"""Sensor platform for Watts SmartHome."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging
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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import WattsCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class WattsSensorEntityDescription(SensorEntityDescription):
    """Describes Watts sensor entity."""

    value_fn: Callable[[dict[str, Any]], Any] | None = None
    exists_fn: Callable[[dict[str, Any]], bool] | None = None


# Smarthome-level sensors
SMARTHOME_SENSORS: tuple[WattsSensorEntityDescription, ...] = (
    WattsSensorEntityDescription(
        key="general_mode",
        name="General Mode",
        icon="mdi:home-automation",
        value_fn=lambda data: data.get("info", {}).get("general_mode"),
    ),
    WattsSensorEntityDescription(
        key="holiday_mode",
        name="Holiday Mode",
        icon="mdi:island",
        value_fn=lambda data: data.get("info", {}).get("holiday_mode"),
    ),
    WattsSensorEntityDescription(
        key="last_connection_diff",
        name="Last Connection",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement="s",
        value_fn=lambda data: data.get("last_connection", {}).get("diff"),
    ),
    WattsSensorEntityDescription(
        key="error_count",
        name="Error Count",
        icon="mdi:alert-circle",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.get("errors", {}).get("errors", [])) if isinstance(data.get("errors", {}).get("errors"), list) else 0,
    ),
)

# Device-level sensors
DEVICE_SENSORS: tuple[WattsSensorEntityDescription, ...] = (
    WattsSensorEntityDescription(
        key="temperature_air",
        name="Air Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda dev: float(dev.get("temperature_air", 0)) if dev.get("temperature_air") else None,
        exists_fn=lambda dev: dev.get("temperature_air") is not None,
    ),
    WattsSensorEntityDescription(
        key="temperature_sol",
        name="Floor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda dev: float(dev.get("temperature_sol", 0)) if dev.get("temperature_sol") else None,
        exists_fn=lambda dev: dev.get("temperature_sol") is not None,
    ),
    WattsSensorEntityDescription(
        key="consigne_confort",
        name="Comfort Setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda dev: float(dev.get("consigne_confort", 0)) if dev.get("consigne_confort") else None,
        exists_fn=lambda dev: dev.get("consigne_confort") is not None,
    ),
    WattsSensorEntityDescription(
        key="consigne_eco",
        name="Eco Setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda dev: float(dev.get("consigne_eco", 0)) if dev.get("consigne_eco") else None,
        exists_fn=lambda dev: dev.get("consigne_eco") is not None,
    ),
    WattsSensorEntityDescription(
        key="heating_up",
        name="Heating Status",
        icon="mdi:radiator",
        value_fn=lambda dev: "Heating" if dev.get("heating_up") == "1" else "Idle",
    ),
    WattsSensorEntityDescription(
        key="error_code",
        name="Error Code",
        icon="mdi:alert",
        value_fn=lambda dev: dev.get("error_code", 0),
    ),
    WattsSensorEntityDescription(
        key="gv_mode",
        name="Operating Mode",
        icon="mdi:thermostat",
        value_fn=lambda dev: dev.get("gv_mode"),
    ),
    WattsSensorEntityDescription(
        key="programme",
        name="Program",
        icon="mdi:calendar-clock",
        value_fn=lambda dev: dev.get("programme"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts SmartHome sensors."""
    coordinator: WattsCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities: list[SensorEntity] = []

    # Create smarthome-level sensors
    for smarthome_id, smarthome_data in coordinator.data.get("smarthomes", {}).items():
        if "error" in smarthome_data:
            continue

        for description in SMARTHOME_SENSORS:
            entities.append(
                WattsSmartHomeSensor(
                    coordinator,
                    description,
                    smarthome_id,
                    smarthome_data.get("info", {}),
                )
            )

        # Create device-level sensors
        details = smarthome_data.get("details", {})
        zones = details.get("zones", [])
        
        for zone in zones:
            for device in zone.get("devices", []):
                device_id = device.get("id_device") or device.get("id")
                if not device_id:
                    continue

                for description in DEVICE_SENSORS:
                    # Skip sensors that don't exist for this device
                    if description.exists_fn and not description.exists_fn(device):
                        continue
                    
                    entities.append(
                        WattsDeviceSensor(
                            coordinator,
                            description,
                            smarthome_id,
                            device_id,
                            device,
                            smarthome_data.get("info", {}),
                        )
                    )

    async_add_entities(entities)


class WattsSmartHomeSensor(CoordinatorEntity[WattsCoordinator], SensorEntity):
    """Representation of a Watts SmartHome sensor."""

    entity_description: WattsSensorEntityDescription

    def __init__(
        self,
        coordinator: WattsCoordinator,
        description: WattsSensorEntityDescription,
        smarthome_id: str,
        smarthome_info: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._smarthome_id = smarthome_id
        self._attr_unique_id = f"{smarthome_id}_{description.key}"
        
        smarthome_label = smarthome_info.get("label", smarthome_id)
        self._attr_name = f"{smarthome_label} {description.name}"
        
        # Device info for grouping entities
        self._attr_device_info = {
            "identifiers": {(DOMAIN, smarthome_id)},
            "name": smarthome_label,
            "manufacturer": "Watts",
            "model": "SmartHome",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        smarthome_data = self.coordinator.get_smarthome_data(self._smarthome_id)
        if not smarthome_data or not self.entity_description.value_fn:
            return None
        
        try:
            return self.entity_description.value_fn(smarthome_data)
        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.debug("Error getting sensor value: %s", err)
            return None


class WattsDeviceSensor(CoordinatorEntity[WattsCoordinator], SensorEntity):
    """Representation of a Watts device sensor."""

    entity_description: WattsSensorEntityDescription

    def __init__(
        self,
        coordinator: WattsCoordinator,
        description: WattsSensorEntityDescription,
        smarthome_id: str,
        device_id: str,
        device_data: dict[str, Any],
        smarthome_info: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._smarthome_id = smarthome_id
        self._device_id = device_id
        self._attr_unique_id = f"{smarthome_id}_{device_id}_{description.key}"
        
        device_label = device_data.get("nom_appareil") or device_data.get("label_interface") or device_id
        self._attr_name = f"{device_label} {description.name}"
        
        # Device info for grouping entities
        smarthome_label = smarthome_info.get("label", smarthome_id)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{smarthome_id}_{device_id}")},
            "name": device_label,
            "manufacturer": "Watts",
            "model": device_data.get("bundle_id", "Device"),
            "via_device": (DOMAIN, smarthome_id),
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        device_data = self.coordinator.get_device_data(self._smarthome_id, self._device_id)
        if not device_data or not self.entity_description.value_fn:
            return None
        
        try:
            return self.entity_description.value_fn(device_data)
        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.debug("Error getting sensor value for device %s: %s", self._device_id, err)
            return None
