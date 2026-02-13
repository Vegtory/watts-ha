"""Select platform for Watts SmartHome."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import WattsApiError
from .const import DATA_API_CLIENT, DATA_COORDINATOR, DEFAULT_LANG, DOMAIN
from .coordinator import WattsCoordinator

_LOGGER = logging.getLogger(__name__)

# Mode mappings - these may need adjustment based on actual API values
OPERATING_MODES = {
    "0": "Off",
    "1": "Comfort",
    "2": "Eco",
    "3": "Frost Protection",
    "4": "Program",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts SmartHome select entities."""
    coordinator: WattsCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    api_client = hass.data[DOMAIN][entry.entry_id][DATA_API_CLIENT]

    entities: list[SelectEntity] = []

    # Create device-level select entities
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

                # Add operating mode select if gv_mode is available
                if device.get("gv_mode") is not None:
                    entities.append(
                        WattsDeviceModeSelect(
                            coordinator,
                            api_client,
                            smarthome_id,
                            device_id,
                            device,
                            smarthome_data.get("info", {}),
                        )
                    )

    async_add_entities(entities)


class WattsDeviceModeSelect(CoordinatorEntity[WattsCoordinator], SelectEntity):
    """Representation of a Watts device mode selector."""

    def __init__(
        self,
        coordinator: WattsCoordinator,
        api_client,
        smarthome_id: str,
        device_id: str,
        device_data: dict[str, Any],
        smarthome_info: dict[str, Any],
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._api_client = api_client
        self._smarthome_id = smarthome_id
        self._device_id = device_id
        self._attr_unique_id = f"{smarthome_id}_{device_id}_mode"
        
        device_label = device_data.get("nom_appareil") or device_data.get("label_interface") or device_id
        self._attr_name = f"{device_label} Mode"
        self._attr_icon = "mdi:thermostat-auto"
        
        self._attr_options = list(OPERATING_MODES.values())
        
        # Device info for grouping entities
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{smarthome_id}_{device_id}")},
            "name": device_label,
            "manufacturer": "Watts",
            "model": device_data.get("bundle_id", "Device"),
            "via_device": (DOMAIN, smarthome_id),
        }

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        device_data = self.coordinator.get_device_data(self._smarthome_id, self._device_id)
        if not device_data:
            return None
        
        mode_value = device_data.get("gv_mode", "0")
        return OPERATING_MODES.get(str(mode_value), "Unknown")

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Find the mode key for the selected option
        mode_key = None
        for key, value in OPERATING_MODES.items():
            if value == option:
                mode_key = key
                break
        
        if mode_key is None:
            _LOGGER.error("Invalid mode option: %s", option)
            return

        try:
            # Push query to change mode
            query_data = {
                "query[gv_mode]": mode_key,
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
            _LOGGER.error("Failed to set mode for device %s: %s", self._device_id, err)
