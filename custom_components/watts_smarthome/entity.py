"""Shared entity classes for Watts SmartHome."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import WattsDataUpdateCoordinator
from .models import WattsDevice, WattsSmarthome

if TYPE_CHECKING:
    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import WattsConfigEntry


def async_setup_device_entities(
    entry: WattsConfigEntry,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[WattsDataUpdateCoordinator, str, str], Iterable[Entity]],
) -> None:
    """Add entities for every thermostat, including ones that appear later."""
    coordinator = entry.runtime_data
    known: set[tuple[str, str]] = set()

    @callback
    def _add_new() -> None:
        new_entities: list[Entity] = []
        for key in sorted(coordinator.device_keys() - known):
            known.add(key)
            new_entities.extend(factory(coordinator, *key))
        if new_entities:
            async_add_entities(new_entities)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


def async_setup_smarthome_entities(
    entry: WattsConfigEntry,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[WattsDataUpdateCoordinator, str], Iterable[Entity]],
) -> None:
    """Add entities for every central unit, including ones that appear later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new_entities: list[Entity] = []
        for smarthome_id in sorted(coordinator.smarthome_ids() - known):
            known.add(smarthome_id)
            new_entities.extend(factory(coordinator, smarthome_id))
        if new_entities:
            async_add_entities(new_entities)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class WattsSmarthomeEntity(CoordinatorEntity[WattsDataUpdateCoordinator]):
    """Base class for entities of the central unit (one per smarthome)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WattsDataUpdateCoordinator, smarthome_id: str, entity_key: str) -> None:
        super().__init__(coordinator)
        self._smarthome_id = smarthome_id
        self._attr_unique_id = f"{smarthome_id}_{entity_key}"
        home = coordinator.get_smarthome(smarthome_id)
        connections = set()
        if home and home.mac_address:
            connections.add((CONNECTION_NETWORK_MAC, format_mac(home.mac_address)))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, smarthome_id)},
            connections=connections,
            name=(home.label if home and home.label else "Watts SmartHome"),
            manufacturer=MANUFACTURER,
            model="SmartHome central unit",
        )

    @property
    def smarthome(self) -> WattsSmarthome | None:
        """Return the smarthome model."""
        return self.coordinator.get_smarthome(self._smarthome_id)

    @property
    def available(self) -> bool:
        """Return True when the smarthome is still reported."""
        return super().available and self.smarthome is not None


class WattsDeviceEntity(CoordinatorEntity[WattsDataUpdateCoordinator]):
    """Base class for all Watts thermostat entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        coordinator: WattsDataUpdateCoordinator,
        smarthome_id: str,
        id_device: str,
        entity_key: str,
    ) -> None:
        """Initialize base entity."""
        super().__init__(coordinator)
        self._smarthome_id = smarthome_id
        self._id_device = id_device
        self._attr_unique_id = f"{smarthome_id}_{id_device}_{entity_key}"

        device = coordinator.get_device(smarthome_id, id_device)
        self._last_device = device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{smarthome_id}_{id_device}")},
            name=device.display_name if device else id_device,
            manufacturer=MANUFACTURER,
            model=f"Bundle {device.bundle_id}" if device and device.bundle_id else "SmartHome thermostat",
            serial_number=id_device,
            suggested_area=(device.zone_name or None) if device else None,
            via_device=(DOMAIN, smarthome_id),
        )

    @property
    def device(self) -> WattsDevice:
        """Return the current device model, or the last known one when it is gone.

        Home Assistant still reads attributes such as min_temp on unavailable
        entities, so this must always return a model.
        """
        device = self.coordinator.get_device(self._smarthome_id, self._id_device)
        if device is not None:
            self._last_device = device
            return device
        assert self._last_device is not None
        return self._last_device

    @property
    def available(self) -> bool:
        """Return True when the device is still reported by the cloud."""
        return super().available and self.coordinator.get_device(self._smarthome_id, self._id_device) is not None


class WattsScheduleAwareEntity(WattsDeviceEntity):
    """Re-renders on every quarter hour, when the weekly schedule can switch."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(self.hass, self._async_quarter_hour, minute=(0, 15, 30, 45), second=1)
        )

    @callback
    def _async_quarter_hour(self, now: datetime) -> None:
        if self.available and self.device.is_program:
            self.async_write_ha_state()
