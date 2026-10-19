"""Binary sensors for Watts SmartHome."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WattsConfigEntry
from .const import MAX_CENTRAL_SILENCE_SECONDS
from .entity import (
    WattsDeviceEntity,
    WattsSmarthomeEntity,
    async_setup_device_entities,
    async_setup_smarthome_entities,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WattsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts binary sensors from a config entry."""
    async_setup_smarthome_entities(
        entry,
        async_add_entities,
        lambda coordinator, smarthome_id: [WattsCentralConnectivity(coordinator, smarthome_id, "connectivity")],
    )
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, smarthome_id, id_device: [
            WattsProblemSensor(
                coordinator=coordinator, smarthome_id=smarthome_id, id_device=id_device, entity_key="problem"
            )
        ],
    )


class WattsProblemSensor(WattsDeviceEntity, BinarySensorEntity):
    """On when the thermostat reports a fault, such as a low battery."""

    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool:
        device = self.device
        return bool(device.errors) or device.error_code != 0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        errors = self.device.errors
        if not errors:
            return None
        return {"errors": [error.title or error.message or error.code for error in errors]}


class WattsCentralConnectivity(WattsSmarthomeEntity, BinarySensorEntity):
    """On when the central unit checked in with the cloud recently.

    Commands are refused while this is off (same rule as the Watts app).
    """

    _attr_translation_key = "central_connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        home = self.smarthome
        if home is None or home.seconds_since_contact is None:
            return False
        return home.seconds_since_contact <= MAX_CENTRAL_SILENCE_SECONDS
