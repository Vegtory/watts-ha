"""Number entities for Watts SmartHome (setpoints and boost duration)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WattsConfigEntry
from .const import (
    ANTI_FROST_MAX_C,
    ANTI_FROST_MIN_C,
    MAX_BOOST_SECONDS,
    MIN_BOOST_SECONDS,
    SETPOINT_ANTI_FROST,
    SETPOINT_BOOST,
    SETPOINT_COMFORT,
    SETPOINT_ECO,
    TEMPERATURE_STEP_C,
)
from .coordinator import WattsDataUpdateCoordinator
from .entity import WattsDeviceEntity, async_setup_device_entities
from .models import clamp_boost_seconds

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class WattsSetpointDescription(NumberEntityDescription):
    """Description of one setpoint control."""

    setpoint_key: str
    fixed_min: float | None = None
    fixed_max: float | None = None


SETPOINTS: tuple[WattsSetpointDescription, ...] = (
    WattsSetpointDescription(key="setpoint_comfort", translation_key="setpoint_comfort", setpoint_key=SETPOINT_COMFORT),
    WattsSetpointDescription(key="setpoint_eco", translation_key="setpoint_eco", setpoint_key=SETPOINT_ECO),
    WattsSetpointDescription(
        key="setpoint_anti_frost",
        translation_key="setpoint_anti_frost",
        setpoint_key=SETPOINT_ANTI_FROST,
        fixed_min=ANTI_FROST_MIN_C,
        fixed_max=ANTI_FROST_MAX_C,
    ),
    WattsSetpointDescription(key="setpoint_boost", translation_key="setpoint_boost", setpoint_key=SETPOINT_BOOST),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WattsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts numbers from a config entry."""

    def factory(coordinator: WattsDataUpdateCoordinator, smarthome_id: str, id_device: str) -> list[NumberEntity]:
        entities: list[NumberEntity] = [
            WattsSetpointNumber(coordinator, smarthome_id, id_device, description) for description in SETPOINTS
        ]
        entities.append(WattsBoostDurationNumber(coordinator, smarthome_id, id_device))
        return entities

    async_setup_device_entities(entry, async_add_entities, factory)


class WattsSetpointNumber(WattsDeviceEntity, NumberEntity):
    """Temperature for one mode (comfort, eco, anti-frost, boost)."""

    entity_description: WattsSetpointDescription
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = TEMPERATURE_STEP_C
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: WattsDataUpdateCoordinator,
        smarthome_id: str,
        id_device: str,
        description: WattsSetpointDescription,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key=description.key,
        )
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.device.get_setpoint(self.entity_description.setpoint_key)

    @property
    def native_min_value(self) -> float:
        if self.entity_description.fixed_min is not None:
            return self.entity_description.fixed_min
        return self.device.min_set_point or 5.0

    @property
    def native_max_value(self) -> float:
        if self.entity_description.fixed_max is not None:
            return self.entity_description.fixed_max
        return self.device.max_set_point or 37.0

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_setpoint(
            self._smarthome_id, self._id_device, self.entity_description.setpoint_key, value
        )


class WattsBoostDurationNumber(WattsDeviceEntity, RestoreNumber):
    """How long boost runs when started from Home Assistant.

    The cloud only learns the duration when boost starts, so the value is kept
    in Home Assistant. Changing it while boost runs restarts boost.
    """

    _attr_translation_key = "boost_duration"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_step = 1
    _attr_native_min_value = MIN_BOOST_SECONDS / 60
    _attr_native_max_value = MAX_BOOST_SECONDS / 60
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: WattsDataUpdateCoordinator, smarthome_id: str, id_device: str) -> None:
        # Keeps the old "boost_timer" unique id so existing entities are reused.
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key="boost_timer",
        )
        self._key = (smarthome_id, id_device)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value:
            self.coordinator.boost_seconds[self._key] = clamp_boost_seconds(int(last.native_value * 60))

    @property
    def native_value(self) -> float:
        return round(self.coordinator.get_boost_seconds(*self._key) / 60)

    async def async_set_native_value(self, value: float) -> None:
        seconds = clamp_boost_seconds(round(value) * 60)
        self.coordinator.boost_seconds[self._key] = seconds
        if self.device.is_boost:
            await self.coordinator.async_set_boost_duration(self._smarthome_id, self._id_device, seconds)
        else:
            self.async_write_ha_state()
