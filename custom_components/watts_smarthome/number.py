"""Number platform for Watts SmartHome."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import WattsApiError
from .const import DATA_API_CLIENT, DATA_COORDINATOR, DEFAULT_LANG, DOMAIN
from .coordinator import WattsCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts SmartHome number entities."""
    coordinator: WattsCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    api_client = hass.data[DOMAIN][entry.entry_id][DATA_API_CLIENT]

    entities: list[NumberEntity] = []

    # Create device-level number entities
    for smarthome_id, smarthome_data in coordinator.data.get("smarthomes", {}).items():
        if "error" in smarthome_data:
            continue

        details = smarthome_data.get("details", {})
        zones = details.get("zones", [])
        
        for zone in zones:
            for device in zone.get("devices", []):
                device_id = device.get("id_device") or device.get("id")
                if not device_id:
                    continue

                # Add manual setpoint number if available
                if device.get("consigne_manuel") is not None:
                    min_temp = float(device.get("min_set_point", 5))
                    max_temp = float(device.get("max_set_point", 30))
                    
                    entities.append(
                        WattsDeviceSetpointNumber(
                            coordinator,
                            api_client,
                            smarthome_id,
                            device_id,
                            device,
                            smarthome_data.get("info", {}),
                            min_temp,
                            max_temp,
                        )
                    )

    async_add_entities(entities)


class WattsDeviceSetpointNumber(CoordinatorEntity[WattsCoordinator], NumberEntity):
    """Representation of a Watts device setpoint."""

    def __init__(
        self,
        coordinator: WattsCoordinator,
        api_client,
        smarthome_id: str,
        device_id: str,
        device_data: dict[str, Any],
        smarthome_info: dict[str, Any],
        min_temp: float,
        max_temp: float,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._api_client = api_client
        self._smarthome_id = smarthome_id
        self._device_id = device_id
        self._attr_unique_id = f"{smarthome_id}_{device_id}_setpoint"
        
        device_label = device_data.get("nom_appareil") or device_data.get("label_interface") or device_id
        self._attr_name = f"{device_label} Manual Setpoint"
        self._attr_icon = "mdi:thermometer"
        
        self._attr_native_min_value = min_temp
        self._attr_native_max_value = max_temp
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_mode = NumberMode.BOX
        
        # Device info for grouping entities
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{smarthome_id}_{device_id}")},
            "name": device_label,
            "manufacturer": "Watts",
            "model": device_data.get("bundle_id", "Device"),
            "via_device": (DOMAIN, smarthome_id),
        }

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        device_data = self.coordinator.get_device_data(self._smarthome_id, self._device_id)
        if not device_data:
            return None
        
        value = device_data.get("consigne_manuel")
        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        try:
            # Push query to change manual setpoint
            query_data = {
                "query[consigne_manuel]": str(value),
                "context": "device",
            }
            
            await self._api_client.async_push_query(
                self._smarthome_id,
                query_data,
                lang=DEFAULT_LANG,
            )
            
            # Refresh coordinator data
            await self.coordinator.async_request_refresh()
            
        except WattsApiError as err:
            _LOGGER.error("Failed to set setpoint for device %s: %s", self._device_id, err)
