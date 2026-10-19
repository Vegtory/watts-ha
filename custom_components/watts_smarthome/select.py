"""Select entities for Watts SmartHome."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WattsConfigEntry
from .const import MODE_PROGRAM_ON, SELECTABLE_MODES
from .entity import WattsDeviceEntity, async_setup_device_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WattsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts mode selects from a config entry."""
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, smarthome_id, id_device: [
            WattsModeSelect(coordinator=coordinator, smarthome_id=smarthome_id, id_device=id_device)
        ],
    )


class WattsModeSelect(WattsDeviceEntity, SelectEntity):
    """Operating mode selector (every mode the app offers)."""

    _attr_translation_key = "mode_selection"
    # The thermostat entity covers the same modes; this one is for automations.
    _attr_entity_registry_enabled_default = False
    _attr_options = list(SELECTABLE_MODES)

    def __init__(self, *, coordinator, smarthome_id: str, id_device: str) -> None:
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key="mode_select",
        )

    @property
    def current_option(self) -> str | None:
        device = self.device
        if device.is_program:
            return MODE_PROGRAM_ON
        mode = device.current_mode
        return mode if mode in SELECTABLE_MODES else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_mode(self._smarthome_id, self._id_device, option)
