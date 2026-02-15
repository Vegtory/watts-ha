"""Number entities for Watts SmartHome controls."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant

from . import get_coordinator
from .const import SETPOINT_ANTI_FROST, SETPOINT_BOOST, SETPOINT_COMFORT, SETPOINT_ECO
from .entity import WattsDeviceEntity


@dataclass(frozen=True, slots=True)
class SetpointNumberDescription:
    """Description of one setpoint control."""

    entity_key: str
    translation_key: str
    setpoint_key: str


SETPOINT_NUMBERS: tuple[SetpointNumberDescription, ...] = (
    SetpointNumberDescription(
        entity_key="setpoint_comfort",
        translation_key="setpoint_comfort",
        setpoint_key=SETPOINT_COMFORT,
    ),
    SetpointNumberDescription(
        entity_key="setpoint_eco",
        translation_key="setpoint_eco",
        setpoint_key=SETPOINT_ECO,
    ),
    SetpointNumberDescription(
        entity_key="setpoint_anti_frost",
        translation_key="setpoint_anti_frost",
        setpoint_key=SETPOINT_ANTI_FROST,
    ),
    SetpointNumberDescription(
        entity_key="setpoint_boost",
        translation_key="setpoint_boost",
        setpoint_key=SETPOINT_BOOST,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Watts numbers from config entry."""
    coordinator = get_coordinator(hass, entry)
    known: set[tuple[str, str, str]] = set()

    def add_missing_entities() -> None:
        new_entities: list[NumberEntity] = []
        for smarthome_id, id_device in sorted(coordinator.device_keys()):
            for description in SETPOINT_NUMBERS:
                key = (smarthome_id, id_device, description.entity_key)
                if key in known:
                    continue
                known.add(key)
                new_entities.append(
                    WattsSetpointNumber(
                        coordinator=coordinator,
                        smarthome_id=smarthome_id,
                        id_device=id_device,
                        description=description,
                    )
                )

            boost_timer_key = (smarthome_id, id_device, "boost_timer")
            if boost_timer_key not in known:
                known.add(boost_timer_key)
                new_entities.append(
                    WattsBoostTimerNumber(
                        coordinator=coordinator,
                        smarthome_id=smarthome_id,
                        id_device=id_device,
                    )
                )

        if new_entities:
            async_add_entities(new_entities)

    add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_missing_entities))


class WattsSetpointNumber(WattsDeviceEntity, NumberEntity):
    """Base number entity for one setpoint type."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        *,
        coordinator,
        smarthome_id: str,
        id_device: str,
        description: SetpointNumberDescription,
    ) -> None:
        """Initialize setpoint number."""
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key=description.entity_key,
        )
        self._description = description
        self._attr_translation_key = description.translation_key

    @property
    def native_value(self) -> float | None:
        """Return setpoint value in Celsius."""
        return self.device.get_setpoint(self._description.setpoint_key)

    @property
    def native_min_value(self) -> float:
        """Return device minimum setpoint."""
        return self.device.min_set_point or 0.0

    @property
    def native_max_value(self) -> float:
        """Return device maximum setpoint."""
        return self.device.max_set_point or 40.0

    async def async_set_native_value(self, value: float) -> None:
        """Set temperature setpoint."""
        await self.coordinator.async_set_setpoint(
            self._smarthome_id,
            self._id_device,
            self._description.setpoint_key,
            value,
        )


class WattsBoostTimerNumber(WattsDeviceEntity, NumberEntity):
    """Number entity for boost timer duration."""

    _attr_translation_key = "boost_timer"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_step = 1
    _attr_native_min_value = 0
    _attr_suggested_display_precision = 0
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-cog"

    def __init__(self, *, coordinator, smarthome_id: str, id_device: str) -> None:
        """Initialize boost timer number."""
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key="boost_timer",
        )

    @property
    def native_max_value(self) -> float:
        """Return a permissive max value for boost timer in minutes."""
        max_seconds = max(14400, self.device.time_boost_seconds, 7200)
        return float(max_seconds / 60)

    @property
    def native_value(self) -> float:
        """Return current boost duration in minutes."""
        return float(self.device.time_boost_seconds / 60)

    async def async_set_native_value(self, value: float) -> None:
        """Set boost timer in minutes."""
        value_seconds = int(round(value * 60))
        await self.coordinator.async_set_boost_timer(
            self._smarthome_id,
            self._id_device,
            value_seconds,
        )
