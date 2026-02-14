"""Sensor platform for Watts SmartHome."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, MODE_CODE_TO_LABEL
from .entity import WattsDeviceEntity
from .helpers import as_int, raw_to_celsius


@dataclass(frozen=True, kw_only=True)
class WattsSensorEntityDescription(SensorEntityDescription):
    """Description for a Watts sensor entity."""

    value_fn: Callable[[dict[str, Any]], StateType]


SENSOR_DESCRIPTIONS: tuple[WattsSensorEntityDescription, ...] = (
    WattsSensorEntityDescription(
        key="current_air_temperature",
        name="Current Air Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: raw_to_celsius(device.get("temperature_air")),
    ),
    WattsSensorEntityDescription(
        key="heating_status",
        name="Heating Status",
        icon="mdi:radiator",
        value_fn=lambda device: "heating"
        if str(device.get("heating_up", "0")) in {"1", "true", "True"}
        else "idle",
    ),
    WattsSensorEntityDescription(
        key="error_code",
        name="Error Code",
        icon="mdi:alert-circle-outline",
        value_fn=lambda device: as_int(device.get("error_code")),
    ),
    WattsSensorEntityDescription(
        key="operating_mode",
        name="Operating Mode",
        icon="mdi:tune-variant",
        value_fn=lambda device: MODE_CODE_TO_LABEL.get(
            str(device.get("gv_mode", "")),
            str(device.get("gv_mode", "unknown")),
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts sensor entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[WattsSensor] = []
    for smarthome_id, device_id in coordinator.iter_device_keys():
        for description in SENSOR_DESCRIPTIONS:
            entities.append(
                WattsSensor(
                    coordinator=coordinator,
                    smarthome_id=smarthome_id,
                    device_id=device_id,
                    description=description,
                )
            )
    async_add_entities(entities)


class WattsSensor(WattsDeviceEntity, SensorEntity):
    """Watts sensor entity."""

    entity_description: WattsSensorEntityDescription

    def __init__(
        self,
        *,
        coordinator,
        smarthome_id: str,
        device_id: str,
        description: WattsSensorEntityDescription,
    ) -> None:
        super().__init__(
            coordinator,
            smarthome_id,
            device_id,
            description.key,
            entity_name=description.name or description.key,
        )
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        device = self._device
        if device is None:
            return None
        return self.entity_description.value_fn(device)
