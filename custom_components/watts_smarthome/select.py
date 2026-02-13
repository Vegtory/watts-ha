"""Select platform for Watts SmartHome."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import WattsApiError
from .const import DATA_API_CLIENT, DATA_COORDINATOR, DEFAULT_LANG, DOMAIN
from .coordinator import WattsCoordinator
from .formatting import device_label

_LOGGER = logging.getLogger(__name__)

# Keep mode selector focused on meaningful user controls.
MODE_LABEL_TO_CODE = {
    "Off": "1",
    "Comfort": "0",
    "Eco": "3",
    "Boost": "4",
    "Program": "8",
}
MODE_CODE_TO_LABEL = {code: label for label, code in MODE_LABEL_TO_CODE.items()}


def _normalize_mode_code(mode_code: str) -> str:
    """Normalize equivalent server mode values to selector options."""
    aliases = {
        "14": "1",
        "12": "0",
        "11": "8",
        "13": "8",
    }
    return aliases.get(mode_code, mode_code)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts SmartHome select entities."""
    coordinator: WattsCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    api_client = hass.data[DOMAIN][entry.entry_id][DATA_API_CLIENT]

    entities: list[SelectEntity] = []

    for smarthome_id, smarthome_data in coordinator.data.get("smarthomes", {}).items():
        if "error" in smarthome_data:
            continue

        for device in coordinator.get_smarthome_devices(smarthome_id):
            device_id = device.get("id_device") or device.get("id")
            if not device_id:
                continue

            if device.get("gv_mode") is None:
                continue

            entities.append(
                WattsDeviceModeSelect(
                    coordinator,
                    api_client,
                    smarthome_id,
                    str(device_id),
                    device,
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
        device_data: dict,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._api_client = api_client
        self._smarthome_id = smarthome_id
        self._device_id = device_id
        self._device_query_id = (
            device_data.get("id")
            if isinstance(device_data.get("id"), str) and device_data.get("id")
            else f"{smarthome_id}#{device_id}"
        )
        self._attr_unique_id = f"{smarthome_id}_{device_id}_mode"
        self._attr_options = list(MODE_LABEL_TO_CODE.keys())
        self._attr_icon = "mdi:thermostat-auto"

        resolved_device_label = device_label(device_data, device_id)
        self._attr_name = f"{resolved_device_label} Mode"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{smarthome_id}_{device_id}")},
            "name": resolved_device_label,
            "manufacturer": "Watts",
            "model": device_data.get("bundle_id", "Device"),
            "via_device": (DOMAIN, smarthome_id),
        }

    def _device_data(self) -> dict | None:
        """Return merged device payload."""
        return self.coordinator.get_device_data(self._smarthome_id, self._device_id)

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        device_data = self._device_data()
        if not device_data:
            return None

        raw_mode = str(device_data.get("gv_mode", ""))
        mode_code = _normalize_mode_code(raw_mode)
        return MODE_CODE_TO_LABEL.get(mode_code)

    def _query_base(self) -> dict[str, str]:
        """Return required protocol fields for device-scoped writes."""
        return {
            "query[id_device]": self._device_id,
            "query[id]": self._device_query_id,
            "peremption": "15000",
            "context": "1",
        }

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        mode_code = MODE_LABEL_TO_CODE.get(option)
        if mode_code is None:
            _LOGGER.error("Invalid mode option: %s", option)
            return

        try:
            query_data = {
                "query[gv_mode]": mode_code,
                "query[nv_mode]": mode_code,
                **self._query_base(),
            }

            # Boost mode requires a timer; default to 60 minutes if unset.
            if mode_code == "4":
                try:
                    current_time_boost = int(float((self._device_data() or {}).get("time_boost", 0)))
                except (TypeError, ValueError):
                    current_time_boost = 0
                if current_time_boost <= 0:
                    query_data["query[time_boost]"] = "3600"

            await self._api_client.async_push_query(
                self._smarthome_id,
                query_data,
                lang=DEFAULT_LANG,
            )
            await self.coordinator.async_request_refresh()

        except WattsApiError as err:
            _LOGGER.error("Failed to set mode for device %s: %s", self._device_id, err)
