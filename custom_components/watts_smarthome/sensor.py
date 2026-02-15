"""Sensor entities for Watts SmartHome."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

from . import get_coordinator
from .const import HEATING_ACTIVE, HEATING_IDLE, MODE_OPTIONS
from .entity import WattsDeviceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Watts sensors from config entry."""
    coordinator = get_coordinator(hass, entry)
    known: set[tuple[str, str, str]] = set()

    def add_missing_entities() -> None:
        new_entities: list[SensorEntity] = []
        for smarthome_id, id_device in sorted(coordinator.device_keys()):
            for entity_cls, entity_key in (
                (WattsCurrentAirTemperatureSensor, "current_air_temperature"),
                (WattsHeatingStatusSensor, "heating_status"),
                (WattsErrorCodeSensor, "error_code"),
                (WattsOperatingModeSensor, "operating_mode"),
            ):
                key = (smarthome_id, id_device, entity_key)
                if key in known:
                    continue
                known.add(key)
                new_entities.append(
                    entity_cls(
                        coordinator=coordinator,
                        smarthome_id=smarthome_id,
                        id_device=id_device,
                    )
                )

        if new_entities:
            async_add_entities(new_entities)

    add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_missing_entities))


class WattsCurrentAirTemperatureSensor(WattsDeviceEntity, SensorEntity):
    """Current air temperature sensor."""

    _attr_translation_key = "current_air_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, *, coordinator, smarthome_id: str, id_device: str) -> None:
        """Initialize temperature sensor."""
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key="current_air_temperature",
        )

    @property
    def native_value(self) -> float | None:
        """Return air temperature in Celsius."""
        return self.device.current_air_temperature


class WattsHeatingStatusSensor(WattsDeviceEntity, SensorEntity):
    """Heating status sensor (idle/heating)."""

    _attr_translation_key = "heating_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [HEATING_IDLE, HEATING_ACTIVE]
    _attr_icon = "mdi:radiator"

    def __init__(self, *, coordinator, smarthome_id: str, id_device: str) -> None:
        """Initialize heating status sensor."""
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key="heating_status",
        )

    @property
    def native_value(self) -> str:
        """Return heating status string."""
        return self.device.heating_status


class WattsErrorCodeSensor(WattsDeviceEntity, SensorEntity):
    """Error code sensor."""

    _attr_translation_key = "error_code"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, *, coordinator, smarthome_id: str, id_device: str) -> None:
        """Initialize error code sensor."""
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key="error_code",
        )

    @property
    def native_value(self) -> int:
        """Return device error code."""
        return self.device.error_code

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return expanded error details when present."""
        if not self.device.errors:
            return None
        return {
            "errors": ", ".join(
                f"{error.code}: {error.title or error.message}".strip() for error in self.device.errors
            )
        }


class WattsOperatingModeSensor(WattsDeviceEntity, SensorEntity):
    """Operating mode sensor."""

    _attr_translation_key = "operating_mode"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_icon = "mdi:thermostat-box"

    def __init__(self, *, coordinator, smarthome_id: str, id_device: str) -> None:
        """Initialize operating mode sensor."""
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key="operating_mode",
        )

    @property
    def options(self) -> list[str]:
        """Return possible mode options including unknown current mode."""
        current = self.device.current_mode
        options = list(MODE_OPTIONS)
        if current not in options:
            options.append(current)
        return options

    @property
    def native_value(self) -> str:
        """Return current mode option."""
        return self.device.current_mode
