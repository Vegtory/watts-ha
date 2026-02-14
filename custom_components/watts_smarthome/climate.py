"""Climate platform for Watts SmartHome."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
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

# Map Watts modes to HVAC modes
# 0: Comfort, 1: Off, 2: Frost, 3: Eco, 4: Boost, 8: Program
WATTS_TO_HVAC_MODE = {
    "0": HVACMode.HEAT,      # Comfort
    "1": HVACMode.OFF,       # Off
    "14": HVACMode.OFF,      # Disabled
    "2": HVACMode.HEAT,      # Frost (still heating, just at low temp)
    "3": HVACMode.AUTO,      # Eco (automated energy saving)
    "4": HVACMode.HEAT,      # Boost (high heat)
    "8": HVACMode.AUTO,      # Program
    "11": HVACMode.AUTO,     # Auto Eco
    "12": HVACMode.HEAT,     # On
    "13": HVACMode.AUTO,     # Auto
}

HVAC_MODE_TO_WATTS = {
    HVACMode.OFF: "1",       # Off
    HVACMode.HEAT: "0",      # Comfort
    HVACMode.AUTO: "8",      # Program
}

DEFAULT_MIN_TEMP = 5.0
DEFAULT_MAX_TEMP = 37.0


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

            # Only create climate entity if device has temperature control
            if device.get("temperature_air") is None and device.get("gv_mode") is None:
                continue

            entities.append(
                WattsClimate(
                    coordinator,
                    api_client,
                    smarthome_id,
                    str(device_id),
                    device,
                )
            )

    async_add_entities(entities)


class WattsClimate(CoordinatorEntity[WattsCoordinator], ClimateEntity):
    """Representation of a Watts climate device."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]

    def __init__(
        self,
        coordinator: WattsCoordinator,
        api_client,
        smarthome_id: str,
        device_id: str,
        device_data: dict[str, Any],
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
        self._attr_name = f"{resolved_device_label}"

        # Set temperature limits from device data
        min_temp = decode_setpoint(device_data.get("min_set_point")) or DEFAULT_MIN_TEMP
        max_temp = decode_setpoint(device_data.get("max_set_point")) or DEFAULT_MAX_TEMP
        self._attr_min_temp = min_temp
        self._attr_max_temp = max_temp
        self._attr_target_temperature_step = 0.5

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{smarthome_id}_{device_id}")},
            "name": resolved_device_label,
            "manufacturer": "Watts",
            "model": device_data.get("bundle_id", "Device"),
            "via_device": (DOMAIN, smarthome_id),
        }

    def _device_data(self) -> dict[str, Any] | None:
        """Return merged device payload."""
        return self.coordinator.get_device_data(self._smarthome_id, self._device_id)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        device_data = self._device_data()
        if not device_data:
            return None
        return decode_temperature(device_data.get("temperature_air"))

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        device_data = self._device_data()
        if not device_data:
            return None

        # Return boost setpoint as target (for quick 1-hour boost control)
        # This makes the climate UI work as: set target = set boost temp, turns on boost for 1 hour
        gv_mode = str(device_data.get("gv_mode", ""))
        
        # If in boost mode, show boost setpoint
        if gv_mode == "4":
            return decode_setpoint(device_data.get("consigne_boost"))
        
        # Otherwise show comfort setpoint (default)
        return decode_setpoint(device_data.get("consigne_confort"))

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        device_data = self._device_data()
        if not device_data:
            return HVACMode.OFF

        gv_mode = str(device_data.get("gv_mode", "1"))
        return WATTS_TO_HVAC_MODE.get(gv_mode, HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        device_data = self._device_data()
        if not device_data:
            return None

        # Check if currently heating
        heating_up = device_data.get("heating_up")
        if str(heating_up) == "1":
            return HVACAction.HEATING

        # If mode is off, return off action
        gv_mode = str(device_data.get("gv_mode", "1"))
        if gv_mode in ("1", "14"):
            return HVACAction.OFF

        return HVACAction.IDLE

    def _query_base(self) -> dict[str, str]:
        """Return required protocol fields for device-scoped writes."""
        return {
            "query[id_device]": self._device_id,
            "query[id]": self._device_query_id,
            "peremption": "15000",
            "context": "1",
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        mode_code = HVAC_MODE_TO_WATTS.get(hvac_mode)
        if mode_code is None:
            _LOGGER.error("Unsupported HVAC mode: %s", hvac_mode)
            return

        try:
            query_data = {
                "query[gv_mode]": mode_code,
                "query[nv_mode]": mode_code,
                **self._query_base(),
            }

            await self._api_client.async_push_query(
                self._smarthome_id,
                query_data,
                lang=DEFAULT_LANG,
            )
            await self.coordinator.async_request_refresh()

        except WattsApiError as err:
            _LOGGER.error("Failed to set HVAC mode for device %s: %s", self._device_id, err)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature.
        
        This implementation sets the boost temperature and activates boost mode for 1 hour,
        providing a quick way to temporarily increase heating.
        """
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        try:
            encoded_temp = encode_setpoint(temperature)
            
            # Set boost temperature and enable boost mode with 1 hour timer
            query_data = {
                "query[consigne_boost]": encoded_temp,
                "query[gv_mode]": "4",  # Boost mode
                "query[nv_mode]": "4",
                "query[time_boost]": "3600",  # 1 hour in seconds
                **self._query_base(),
            }

            await self._api_client.async_push_query(
                self._smarthome_id,
                query_data,
                lang=DEFAULT_LANG,
            )
            await self.coordinator.async_request_refresh()

        except WattsApiError as err:
            _LOGGER.error(
                "Failed to set temperature for device %s: %s",
                self._device_id,
                err,
            )
