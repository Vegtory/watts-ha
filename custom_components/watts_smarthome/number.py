"""Number platform for Watts SmartHome."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_MAX_TEMP_C, DEFAULT_MIN_TEMP_C, DOMAIN
from .entity import WattsDeviceEntity
from .helpers import as_int, celsius_to_raw, raw_to_celsius
from . import WattsRuntimeData


@dataclass(frozen=True, kw_only=True)
class WattsSetpointDescription(NumberEntityDescription):
    """Description for a setpoint number entity."""

    query_field: str


SETPOINT_DESCRIPTIONS: tuple[WattsSetpointDescription, ...] = (
    WattsSetpointDescription(
        key="setpoint_comfort",
        name="Setpoint Comfort",
        icon="mdi:thermometer-chevron-up",
        query_field="consigne_confort",
    ),
    WattsSetpointDescription(
        key="setpoint_eco",
        name="Setpoint Eco",
        icon="mdi:leaf",
        query_field="consigne_eco",
    ),
    WattsSetpointDescription(
        key="setpoint_anti_frost",
        name="Setpoint Anti-frost",
        icon="mdi:snowflake-thermometer",
        query_field="consigne_hg",
    ),
    WattsSetpointDescription(
        key="setpoint_boost",
        name="Setpoint Boost",
        icon="mdi:rocket-launch",
        query_field="consigne_boost",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts number entities."""
    runtime: WattsRuntimeData = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator

    entities: list[NumberEntity] = []
    for smarthome_id, device_id in coordinator.iter_device_keys():
        for description in SETPOINT_DESCRIPTIONS:
            entities.append(
                WattsSetpointNumber(
                    coordinator=coordinator,
                    smarthome_id=smarthome_id,
                    device_id=device_id,
                    description=description,
                )
            )
        entities.append(
            WattsBoostTimeoutNumber(
                coordinator=coordinator,
                smarthome_id=smarthome_id,
                device_id=device_id,
            )
        )

    async_add_entities(entities)


class WattsSetpointNumber(WattsDeviceEntity, NumberEntity):
    """Setpoint control number for Watts devices."""

    entity_description: WattsSetpointDescription

    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 0.5

    def __init__(
        self,
        *,
        coordinator,
        smarthome_id: str,
        device_id: str,
        description: WattsSetpointDescription,
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
    def native_min_value(self) -> float:
        device = self._device
        if device is None:
            return DEFAULT_MIN_TEMP_C
        raw_min = raw_to_celsius(device.get("min_set_point"))
        return raw_min if raw_min is not None else DEFAULT_MIN_TEMP_C

    @property
    def native_max_value(self) -> float:
        device = self._device
        if device is None:
            return DEFAULT_MAX_TEMP_C
        raw_max = raw_to_celsius(device.get("max_set_point"))
        return raw_max if raw_max is not None else DEFAULT_MAX_TEMP_C

    @property
    def native_value(self) -> float | None:
        device = self._device
        if device is None:
            return None
        return raw_to_celsius(device.get(self.entity_description.query_field))

    async def async_set_native_value(self, value: float) -> None:
        bounded = max(self.native_min_value, min(float(value), self.native_max_value))
        await self.coordinator.async_push_device_update(
            self._smarthome_id,
            self._device_id,
            {self.entity_description.query_field: celsius_to_raw(bounded)},
        )


class WattsBoostTimeoutNumber(WattsDeviceEntity, NumberEntity):
    """Boost timeout number entity."""

    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = 240
    _attr_native_step = 1
    _attr_icon = "mdi:timer-outline"

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
            "boost_timeout",
            entity_name="Boost Timeout",
        )

    @property
    def native_value(self) -> float | None:
        device = self._device
        if device is None:
            return None
        seconds = as_int(device.get("time_boost"))
        if seconds is None:
            return None
        return round(seconds / 60.0, 1)

    async def async_set_native_value(self, value: float) -> None:
        seconds = max(0, int(round(float(value) * 60)))
        await self.coordinator.async_push_device_update(
            self._smarthome_id,
            self._device_id,
            {"time_boost": seconds},
        )
