"""Climate platform for Watts SmartHome."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    PRESET_COMFORT,
    PRESET_ECO,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import WattsApiError
from .const import DATA_API_CLIENT, DATA_COORDINATOR, DEFAULT_LANG, DOMAIN
from .coordinator import WattsCoordinator
from .formatting import decode_setpoint, decode_temperature, device_label, encode_setpoint

_LOGGER = logging.getLogger(__name__)

# Mode values confirmed from documented third-party protocol implementations.
MODE_COMFORT = "0"
MODE_OFF = "1"
MODE_ECO = "3"
MODE_AUTO = "8"

OFF_MODE_CODES = {MODE_OFF, "14"}
AUTO_MODE_CODES = {MODE_AUTO, "11", "13"}
ECO_MODE_CODES = {MODE_ECO}
COMFORT_MODE_CODES = {MODE_COMFORT, "12"}


def normalize_mode_code(mode_code: str) -> str:
    """Normalize raw gv_mode/nv_mode into the canonical control set."""
    if mode_code in OFF_MODE_CODES:
        return MODE_OFF
    if mode_code in AUTO_MODE_CODES:
        return MODE_AUTO
    if mode_code in ECO_MODE_CODES:
        return MODE_ECO
    if mode_code in COMFORT_MODE_CODES:
        return MODE_COMFORT
    return mode_code


def target_field_for_mode(mode_code: str) -> str:
    """Return the active setpoint field for a given mode code."""
    normalized_mode = normalize_mode_code(mode_code)
    if normalized_mode == MODE_ECO:
        return "consigne_eco"
    if normalized_mode == "2":
        return "consigne_hg"
    if normalized_mode == "4":
        return "consigne_boost"
    return "consigne_confort"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts SmartHome climate entities."""
    coordinator: WattsCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    api_client = hass.data[DOMAIN][entry.entry_id][DATA_API_CLIENT]

    entities: list[ClimateEntity] = []

    for smarthome_id, smarthome_data in coordinator.data.get("smarthomes", {}).items():
        if "error" in smarthome_data:
            continue

        for device in coordinator.get_smarthome_devices(smarthome_id):
            device_id = device.get("id_device") or device.get("id")
            if not device_id:
                continue

            if device.get("consigne_manuel") is None and device.get("gv_mode") is None:
                continue

            entities.append(
                WattsDeviceClimate(
                    coordinator,
                    api_client,
                    smarthome_id,
                    str(device_id),
                    device,
                    smarthome_data.get("info", {}),
                )
            )

    async_add_entities(entities)


class WattsDeviceClimate(CoordinatorEntity[WattsCoordinator], ClimateEntity):
    """Representation of a Watts heating thermostat."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.1
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_preset_modes = [PRESET_COMFORT, PRESET_ECO]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(
        self,
        coordinator: WattsCoordinator,
        api_client,
        smarthome_id: str,
        device_id: str,
        device_data: dict[str, Any],
        smarthome_info: dict[str, Any],
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._api_client = api_client
        self._smarthome_id = smarthome_id
        self._device_id = device_id
        self._device_query_id = (
            device_data.get("id")
            if isinstance(device_data.get("id"), str) and device_data.get("id")
            else f"{smarthome_id}#{device_id}"
        )

        self._attr_unique_id = f"{smarthome_id}_{device_id}_climate"
        resolved_device_label = device_label(device_data, device_id)
        self._attr_name = resolved_device_label

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{smarthome_id}_{device_id}")},
            "name": resolved_device_label,
            "manufacturer": "Watts",
            "model": device_data.get("bundle_id", "Device"),
            "via_device": (DOMAIN, smarthome_id),
        }

    def _device_data(self) -> dict[str, Any] | None:
        """Return merged device payload from coordinator."""
        return self.coordinator.get_device_data(self._smarthome_id, self._device_id)

    @property
    def min_temp(self) -> float:
        """Return the minimum supported temperature."""
        device_data = self._device_data() or {}
        return decode_setpoint(device_data.get("min_set_point")) or 5.0

    @property
    def max_temp(self) -> float:
        """Return the maximum supported temperature."""
        device_data = self._device_data() or {}
        return decode_setpoint(device_data.get("max_set_point")) or 30.0

    @property
    def current_temperature(self) -> float | None:
        """Return current room temperature."""
        device_data = self._device_data()
        if not device_data:
            return None
        return decode_temperature(device_data.get("temperature_air"))

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        device_data = self._device_data()
        if not device_data:
            return None
        mode_code = str(device_data.get("gv_mode", ""))
        field_name = target_field_for_mode(mode_code)
        value = decode_setpoint(device_data.get(field_name))
        if value is not None:
            return value
        return decode_setpoint(device_data.get("consigne_manuel"))

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        device_data = self._device_data() or {}
        mode_code = normalize_mode_code(str(device_data.get("gv_mode", MODE_COMFORT)))
        if mode_code == MODE_OFF:
            return HVACMode.OFF
        if mode_code == MODE_AUTO:
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        """Return current HVAC action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        device_data = self._device_data() or {}
        if str(device_data.get("heating_up", "0")) == "1":
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return active preset mode."""
        device_data = self._device_data()
        if not device_data:
            return None
        mode_code = normalize_mode_code(str(device_data.get("gv_mode", "")))
        if mode_code == MODE_ECO:
            return PRESET_ECO
        if mode_code == MODE_COMFORT:
            return PRESET_COMFORT
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose raw mode/program fields for troubleshooting and automations."""
        device_data = self._device_data() or {}
        return {
            "gv_mode_code": str(device_data.get("gv_mode", "")),
            "programme": device_data.get("programme"),
            "zone_label": device_data.get("zone_label"),
            "id_device": self._device_id,
        }

    async def _async_push_device_query(self, query_data: dict[str, Any]) -> None:
        """Send a device-scoped query and refresh state."""
        await self._api_client.async_push_query(
            self._smarthome_id,
            {
                **query_data,
                "query[id_device]": self._device_id,
                "query[id]": self._device_query_id,
                "peremption": "15000",
                "context": "1",
            },
            lang=DEFAULT_LANG,
        )
        await self.coordinator.async_request_refresh()

    def _build_mode_setpoint_payload(self, mode_code: str, temperature: float) -> dict[str, Any]:
        """Build a protocol-compatible mode/setpoint payload."""
        encoded_setpoint = encode_setpoint(temperature)
        return {
            "query[time_boost]": "0",
            "query[consigne_confort]": encoded_setpoint,
            "query[consigne_manuel]": encoded_setpoint,
            "query[gv_mode]": mode_code,
            "query[nv_mode]": mode_code,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        try:
            current_mode = normalize_mode_code(
                str((self._device_data() or {}).get("gv_mode", MODE_COMFORT))
            )
            await self._async_push_device_query(
                self._build_mode_setpoint_payload(current_mode, float(temperature))
            )
        except (TypeError, ValueError, WattsApiError) as err:
            _LOGGER.error("Failed to set temperature for device %s: %s", self._device_id, err)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        current_mode_code = normalize_mode_code(
            str((self._device_data() or {}).get("gv_mode", MODE_COMFORT))
        )
        current_target = self.target_temperature
        if current_target is None:
            current_target = decode_setpoint(
                (self._device_data() or {}).get("consigne_confort")
            ) or 20.0

        if hvac_mode == HVACMode.OFF:
            mode_code = MODE_OFF
        elif hvac_mode == HVACMode.AUTO:
            mode_code = MODE_AUTO
        elif hvac_mode == HVACMode.HEAT:
            if current_mode_code == MODE_ECO:
                mode_code = MODE_ECO
            else:
                mode_code = MODE_COMFORT
        else:
            _LOGGER.error("Unsupported HVAC mode for device %s: %s", self._device_id, hvac_mode)
            return

        try:
            await self._async_push_device_query(
                self._build_mode_setpoint_payload(mode_code, float(current_target))
            )
        except WattsApiError as err:
            _LOGGER.error("Failed to set HVAC mode for device %s: %s", self._device_id, err)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode."""
        current_target = self.target_temperature
        if current_target is None:
            current_target = decode_setpoint(
                (self._device_data() or {}).get("consigne_confort")
            ) or 20.0

        if preset_mode == PRESET_COMFORT:
            mode_code = MODE_COMFORT
        elif preset_mode == PRESET_ECO:
            mode_code = MODE_ECO
        else:
            _LOGGER.error("Unsupported preset mode for device %s: %s", self._device_id, preset_mode)
            return

        try:
            await self._async_push_device_query(
                self._build_mode_setpoint_payload(mode_code, float(current_target))
            )
        except WattsApiError as err:
            _LOGGER.error("Failed to set preset mode for device %s: %s", self._device_id, err)

    async def async_turn_on(self) -> None:
        """Turn climate entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn climate entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
