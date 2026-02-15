"""Shared entity classes for Watts SmartHome."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WattsDataUpdateCoordinator
from .models import WattsDevice


class WattsDeviceEntity(CoordinatorEntity[WattsDataUpdateCoordinator]):
    """Base class for all Watts device entities."""

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
        self._entity_key = entity_key
        self._attr_unique_id = f"{smarthome_id}_{id_device}_{entity_key}"

    @property
    def device(self) -> WattsDevice:
        """Return current device model from coordinator."""
        return self.coordinator.get_device(self._smarthome_id, self._id_device)

    @property
    def device_info(self) -> DeviceInfo:
        """Return registry metadata for this thermostat/zone device."""
        device = self.device
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._smarthome_id}_{self._id_device}")},
            name=device.display_name,
            manufacturer="Watts Electronics",
            model=f"Bundle {device.bundle_id}" if device.bundle_id else "SmartHome Thermostat",
            serial_number=device.id_device,
            suggested_area=device.zone_name or None,
        )
