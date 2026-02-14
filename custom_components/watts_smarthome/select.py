"""Select platform for Watts SmartHome."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MODE_CODE_TO_OPTION, MODE_OPTION_TO_CODE
from .entity import WattsDeviceEntity
from . import WattsRuntimeData

MODE_OPTIONS = list(MODE_OPTION_TO_CODE)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts mode select entities."""
    runtime: WattsRuntimeData = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator

    entities: list[WattsModeSelect] = []
    for smarthome_id, device_id in coordinator.iter_device_keys():
        entities.append(
            WattsModeSelect(
                coordinator=coordinator,
                smarthome_id=smarthome_id,
                device_id=device_id,
            )
        )

    async_add_entities(entities)


class WattsModeSelect(WattsDeviceEntity, SelectEntity):
    """Select entity for device operating mode."""

    _attr_options = MODE_OPTIONS
    _attr_icon = "mdi:cached"

    def __init__(
        self,
        *,
        coordinator,
        smarthome_id: str,
        device_id: str,
    ) -> None:
        super().__init__(
            coordinator,
            smarthome_id,
            device_id,
            "mode",
            entity_name="Mode",
        )

    @property
    def current_option(self) -> str | None:
        device = self._device
        if device is None:
            return None
        mode_code = str(device.get("gv_mode", ""))
        return MODE_CODE_TO_OPTION.get(mode_code, MODE_OPTIONS[0])

    async def async_select_option(self, option: str) -> None:
        if option not in MODE_OPTION_TO_CODE:
            raise ValueError(f"Unsupported Watts mode option: {option}")
        mode_code = MODE_OPTION_TO_CODE[option]
        await self.coordinator.async_push_device_update(
            self._smarthome_id,
            self._device_id,
            {"gv_mode": mode_code, "nv_mode": mode_code},
        )
