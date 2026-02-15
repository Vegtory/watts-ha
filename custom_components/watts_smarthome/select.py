"""Select entities for Watts SmartHome."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import get_coordinator
from .const import MODE_OPTIONS
from .entity import WattsDeviceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Watts mode selects from config entry."""
    coordinator = get_coordinator(hass, entry)
    known: set[tuple[str, str]] = set()

    def add_missing_entities() -> None:
        new_entities: list[WattsModeSelect] = []
        for smarthome_id, id_device in sorted(coordinator.device_keys()):
            key = (smarthome_id, id_device)
            if key in known:
                continue
            known.add(key)
            new_entities.append(
                WattsModeSelect(
                    coordinator=coordinator,
                    smarthome_id=smarthome_id,
                    id_device=id_device,
                )
            )

        if new_entities:
            async_add_entities(new_entities)

    add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_missing_entities))


class WattsModeSelect(WattsDeviceEntity, SelectEntity):
    """Device operating mode selector."""

    _attr_translation_key = "mode_selection"
    _attr_icon = "mdi:thermostat"

    def __init__(
        self,
        *,
        coordinator,
        smarthome_id: str,
        id_device: str,
    ) -> None:
        """Initialize select entity."""
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key="mode_select",
        )

    @property
    def options(self) -> list[str]:
        """Return selectable mode options."""
        current = self.device.current_mode
        options = list(MODE_OPTIONS)
        if current not in options:
            options.append(current)
        return options

    @property
    def current_option(self) -> str:
        """Return currently selected mode."""
        return self.device.current_mode

    async def async_select_option(self, option: str) -> None:
        """Change device mode."""
        await self.coordinator.async_set_mode(self._smarthome_id, self._id_device, option)
