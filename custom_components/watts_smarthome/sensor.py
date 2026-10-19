"""Sensor entities for Watts SmartHome."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import WattsConfigEntry
from .const import ALL_MODES, HEATING_ACTIVE, HEATING_IDLE
from .coordinator import WattsDataUpdateCoordinator
from .entity import (
    WattsDeviceEntity,
    WattsScheduleAwareEntity,
    WattsSmarthomeEntity,
    async_setup_device_entities,
    async_setup_smarthome_entities,
)
from .models import WattsDevice

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class WattsDeviceSensorDescription(SensorEntityDescription):
    """Description of a thermostat sensor."""

    value_fn: Callable[[WattsDevice], Any]
    attributes_fn: Callable[[WattsDevice], dict[str, Any] | None] = lambda _: None


def _next_change(device: WattsDevice) -> datetime | None:
    if not device.is_program:
        return None
    _, change = device.schedule_now(dt_util.now())
    return change.at if change else None


def _next_change_attributes(device: WattsDevice) -> dict[str, Any] | None:
    if not device.is_program:
        return None
    _, change = device.schedule_now(dt_util.now())
    if change is None:
        return None
    return {"next_period": change.period, "next_temperature": device.schedule_temperature(change.period)}


def _error_attributes(device: WattsDevice) -> dict[str, Any] | None:
    if not device.errors:
        return None
    return {"errors": [{"code": e.code, "title": e.title or e.message} for e in device.errors]}


DEVICE_SENSORS: tuple[WattsDeviceSensorDescription, ...] = (
    WattsDeviceSensorDescription(
        key="current_air_temperature",
        translation_key="current_air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.current_air_temperature,
    ),
    WattsDeviceSensorDescription(
        key="floor_temperature",
        translation_key="floor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.current_floor_temperature,
    ),
    WattsDeviceSensorDescription(
        # Only set while the thermostat follows its schedule (Auto).
        key="next_schedule_change",
        translation_key="next_schedule_change",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_change,
        attributes_fn=_next_change_attributes,
    ),
    WattsDeviceSensorDescription(
        key="heating_status",
        translation_key="heating_status",
        device_class=SensorDeviceClass.ENUM,
        options=[HEATING_IDLE, HEATING_ACTIVE],
        value_fn=lambda device: device.heating_status,
    ),
    WattsDeviceSensorDescription(
        key="operating_mode",
        translation_key="operating_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(ALL_MODES),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.current_mode if device.current_mode in ALL_MODES else None,
    ),
    WattsDeviceSensorDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        # The "Problem" binary sensor shows the same information readably.
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.error_code,
        attributes_fn=_error_attributes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WattsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts sensors from a config entry."""
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, smarthome_id, id_device: [
            (WattsScheduleSensor if description.key == "next_schedule_change" else WattsDeviceSensor)(
                coordinator, smarthome_id, id_device, description
            )
            for description in DEVICE_SENSORS
        ],
    )
    async_setup_smarthome_entities(
        entry,
        async_add_entities,
        lambda coordinator, smarthome_id: [
            WattsLastContactSensor(coordinator, smarthome_id, "last_contact"),
            WattsCommandStatusSensor(coordinator, smarthome_id, "command_status"),
        ],
    )


class WattsDeviceSensor(WattsDeviceEntity, SensorEntity):
    """A thermostat sensor."""

    entity_description: WattsDeviceSensorDescription

    def __init__(
        self,
        coordinator: WattsDataUpdateCoordinator,
        smarthome_id: str,
        id_device: str,
        description: WattsDeviceSensorDescription,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key=description.key,
        )
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.device)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attributes_fn(self.device)


class WattsScheduleSensor(WattsScheduleAwareEntity, WattsDeviceSensor):
    """Next schedule change; refreshed on each quarter hour."""


class WattsLastContactSensor(WattsSmarthomeEntity, SensorEntity):
    """Seconds since the central unit last checked in with the cloud."""

    _attr_translation_key = "last_contact"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> int | None:
        home = self.smarthome
        return home.seconds_since_contact if home else None


class WattsCommandStatusSensor(WattsSmarthomeEntity, SensorEntity):
    """Result of the last command sent to this central unit."""

    _attr_translation_key = "command_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "sending", "sent", "delivered", "failed"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        return self.coordinator.sync_state(self._smarthome_id).status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sync = self.coordinator.sync_state(self._smarthome_id)
        return {
            "timeout_seconds": sync.peremption_ms / 1000,
            "awaiting_confirmation": self.coordinator.has_pending(self._smarthome_id),
        }
