"""Climate platform for Watts SmartHome."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    PRESET_BOOST,
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

PRESET_FROST = "frost_protection"
PRESET_AUTO = "auto"
PRESET_AUTO_COMFORT = "auto_comfort"
PRESET_AUTO_ECO = "auto_eco"
PRESET_ON = "on"

PRESET_TO_MODE_CODE: dict[str, str] = {
    PRESET_COMFORT: "0",
    PRESET_FROST: "2",
    PRESET_ECO: "3",
    PRESET_BOOST: "4",
    PRESET_AUTO_COMFORT: "8",
    PRESET_AUTO_ECO: "11",
    PRESET_ON: "12",
    PRESET_AUTO: "13",
}
MODE_CODE_TO_PRESET: dict[str, str] = {
    mode_code: preset for preset, mode_code in PRESET_TO_MODE_CODE.items()
}
AUTO_MODE_CODES = {"8", "11", "13"}
OFF_MODE_CODES = {"1", "14"}

MODE_CODE_TO_SETPOINT_FIELD: dict[str, str] = {
    "0": "consigne_confort",  # comfort
    "2": "consigne_hg",  # frost protection
    "3": "consigne_eco",  # eco
    "4": "consigne_boost",  # boost
    "8": "consigne_confort",  # auto comfort
    "11": "consigne_eco",  # auto eco
}


def target_field_for_mode(mode_code: str) -> str:
    """Return the best setpoint field for a given mode code."""
    return MODE_CODE_TO_SETPOINT_FIELD.get(mode_code, "consigne_manuel")


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
    _attr_preset_modes = list(PRESET_TO_MODE_CODE.keys())
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
        mode_code = str(device_data.get("gv_mode", "0"))
        if mode_code in OFF_MODE_CODES:
            return HVACMode.OFF
        if mode_code in AUTO_MODE_CODES:
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
        mode_code = str(device_data.get("gv_mode", ""))
        return MODE_CODE_TO_PRESET.get(mode_code)

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
                "context": "device",
            },
            lang=DEFAULT_LANG,
        )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        try:
            mode_code = str((self._device_data() or {}).get("gv_mode", ""))
            target_field = target_field_for_mode(mode_code)
            await self._async_push_device_query(
                {f"query[{target_field}]": encode_setpoint(float(temperature))}
            )
        except (TypeError, ValueError, WattsApiError) as err:
            _LOGGER.error("Failed to set temperature for device %s: %s", self._device_id, err)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        current_mode_code = str((self._device_data() or {}).get("gv_mode", "0"))

        if hvac_mode == HVACMode.OFF:
            mode_code = "1"
        elif hvac_mode == HVACMode.AUTO:
            mode_code = current_mode_code if current_mode_code in AUTO_MODE_CODES else "13"
        elif hvac_mode == HVACMode.HEAT:
            if current_mode_code in OFF_MODE_CODES or current_mode_code in AUTO_MODE_CODES:
                mode_code = "0"
            else:
                mode_code = current_mode_code
        else:
            _LOGGER.error("Unsupported HVAC mode for device %s: %s", self._device_id, hvac_mode)
            return

        try:
            await self._async_push_device_query({"query[gv_mode]": mode_code})
        except WattsApiError as err:
            _LOGGER.error("Failed to set HVAC mode for device %s: %s", self._device_id, err)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode."""
        mode_code = PRESET_TO_MODE_CODE.get(preset_mode)
        if mode_code is None:
            _LOGGER.error("Unsupported preset mode for device %s: %s", self._device_id, preset_mode)
            return
        try:
            await self._async_push_device_query({"query[gv_mode]": mode_code})
        except WattsApiError as err:
            _LOGGER.error("Failed to set preset mode for device %s: %s", self._device_id, err)

    async def async_turn_on(self) -> None:
        """Turn climate entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn climate entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
