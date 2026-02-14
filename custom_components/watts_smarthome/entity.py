"""Shared entity classes for Watts SmartHome."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WattsDataUpdateCoordinator


class WattsDeviceEntity(CoordinatorEntity[WattsDataUpdateCoordinator]):
    """Base class for Watts device entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WattsDataUpdateCoordinator,
        smarthome_id: str,
        device_id: str,
        unique_suffix: str,
        *,
        entity_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._smarthome_id = smarthome_id
        self._device_id = device_id
        self._attr_unique_id = f"{smarthome_id}_{device_id}_{unique_suffix}"
        self._attr_name = entity_name

    @property
    def _device(self) -> dict[str, Any] | None:
        return self.coordinator.get_device(self._smarthome_id, self._device_id)

    @property
    def available(self) -> bool:
        return super().available and self._device is not None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._smarthome_id}_{self._device_id}")},
            name=self.coordinator.get_device_name(self._smarthome_id, self._device_id),
            manufacturer="Watts",
            model="SmartHome",
            serial_number=self._device_id,
        )
