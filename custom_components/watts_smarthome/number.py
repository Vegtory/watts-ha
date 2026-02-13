"""Number platform for Watts SmartHome."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.number import NumberEntity
try:
    from homeassistant.components.number import NumberMode
except ImportError:  # pragma: no cover - compatibility with older HA cores
    NumberMode = None  # type: ignore[assignment]
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
try:
    from homeassistant.const import UnitOfTime
except ImportError:  # pragma: no cover - compatibility with older HA cores
    class UnitOfTime:  # type: ignore[no-redef]
        """Fallback time units for older Home Assistant cores."""

        MINUTES = "min"
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import WattsApiError
from .const import DATA_API_CLIENT, DATA_COORDINATOR, DEFAULT_LANG, DOMAIN
from .coordinator import WattsCoordinator
from .formatting import decode_setpoint, device_label, encode_setpoint

_LOGGER = logging.getLogger(__name__)

DEFAULT_MIN_TEMP = 5.0
DEFAULT_MAX_TEMP = 37.0


@dataclass(frozen=True)
class WattsNumberEntityDescription:
    """Describes a Watts number entity."""

    key: str
    name: str
    field: str
    icon: str
    is_temperature: bool = True
    native_step: float = 0.1
    native_min_value: float | None = None
    native_max_value: float | None = None
    native_unit: str | None = UnitOfTemperature.CELSIUS


DEVICE_NUMBERS: tuple[WattsNumberEntityDescription, ...] = (
    WattsNumberEntityDescription(
        key="comfort_setpoint",
        name="Comfort Setpoint",
        field="consigne_confort",
        icon="mdi:thermometer-chevron-up",
    ),
    WattsNumberEntityDescription(
        key="eco_setpoint",
        name="Eco Setpoint",
        field="consigne_eco",
        icon="mdi:leaf",
    ),
    WattsNumberEntityDescription(
        key="boost_setpoint",
        name="Boost Setpoint",
        field="consigne_boost",
        icon="mdi:rocket-launch",
    ),
    WattsNumberEntityDescription(
        key="manual_setpoint",
        name="Manual Setpoint",
        field="consigne_manuel",
        icon="mdi:thermometer",
    ),
    WattsNumberEntityDescription(
        key="frost_setpoint",
        name="Frost Setpoint",
        field="consigne_hg",
        icon="mdi:snowflake-thermometer",
    ),
    WattsNumberEntityDescription(
        key="boost_timer",
        name="Boost Timer",
        field="time_boost",
        icon="mdi:timer-cog",
        is_temperature=False,
        native_step=1.0,
        native_min_value=0.0,
        native_max_value=240.0,
        native_unit=UnitOfTime.MINUTES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts SmartHome number entities."""
    coordinator: WattsCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    api_client = hass.data[DOMAIN][entry.entry_id][DATA_API_CLIENT]

    entities: list[NumberEntity] = []

    for smarthome_id, smarthome_data in coordinator.data.get("smarthomes", {}).items():
        if "error" in smarthome_data:
            continue

        for device in coordinator.get_smarthome_devices(smarthome_id):
            device_id = device.get("id_device") or device.get("id")
            if not device_id:
                continue

            for description in DEVICE_NUMBERS:
                entities.append(
                    WattsDeviceConfigNumber(
                        coordinator=coordinator,
                        api_client=api_client,
                        description=description,
                        smarthome_id=smarthome_id,
                        device_id=str(device_id),
                        device_data=device,
                    )
                )

    async_add_entities(entities)


class WattsDeviceConfigNumber(CoordinatorEntity[WattsCoordinator], NumberEntity):
    """Representation of a Watts device numeric setting."""

    entity_description: WattsNumberEntityDescription

    def __init__(
        self,
        coordinator: WattsCoordinator,
        api_client,
        description: WattsNumberEntityDescription,
        smarthome_id: str,
        device_id: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._api_client = api_client
        self.entity_description = description
        self._smarthome_id = smarthome_id
        self._device_id = device_id
        self._device_query_id = (
            device_data.get("id")
            if isinstance(device_data.get("id"), str) and device_data.get("id")
            else f"{smarthome_id}#{device_id}"
        )
        self._attr_unique_id = f"{smarthome_id}_{device_id}_{description.key}"
        self._attr_icon = description.icon
        self._attr_mode = NumberMode.BOX if NumberMode is not None else "box"
        self._attr_native_step = description.native_step
        self._attr_native_unit_of_measurement = description.native_unit

        if description.is_temperature:
            min_temp = decode_setpoint(device_data.get("min_set_point")) or DEFAULT_MIN_TEMP
            max_temp = decode_setpoint(device_data.get("max_set_point")) or DEFAULT_MAX_TEMP
            self._attr_native_min_value = min_temp
            self._attr_native_max_value = max_temp
        else:
            self._attr_native_min_value = (
                description.native_min_value if description.native_min_value is not None else 0.0
            )
            self._attr_native_max_value = (
                description.native_max_value if description.native_max_value is not None else 240.0
            )

        resolved_device_label = device_label(device_data, device_id)
        self._attr_name = f"{resolved_device_label} {description.name}"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{smarthome_id}_{device_id}")},
            "name": resolved_device_label,
            "manufacturer": "Watts",
            "model": device_data.get("bundle_id", "Device"),
            "via_device": (DOMAIN, smarthome_id),
        }

    def _device_data(self) -> dict[str, Any] | None:
        """Return merged device payload."""
        return self.coordinator.get_device_data(self._smarthome_id, self._device_id)

    @property
    def native_value(self) -> float | None:
        """Return the current numeric value."""
        device_data = self._device_data()
        if not device_data:
            return None

        raw_value = device_data.get(self.entity_description.field)
        if self.entity_description.is_temperature:
            return decode_setpoint(raw_value)

        try:
            return round(float(raw_value) / 60.0, 1)
        except (TypeError, ValueError):
            return None

    def _query_base(self) -> dict[str, str]:
        """Return required protocol fields for device-scoped writes."""
        return {
            "query[id_device]": self._device_id,
            "query[id]": self._device_query_id,
            "peremption": "15000",
            "context": "1",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set a new numeric value."""
        try:
            if self.entity_description.is_temperature:
                encoded_value = encode_setpoint(value)
            else:
                encoded_value = str(max(0, int(round(float(value) * 60.0))))

            query_data = {
                f"query[{self.entity_description.field}]": encoded_value,
                **self._query_base(),
            }

            await self._api_client.async_push_query(
                self._smarthome_id,
                query_data,
                lang=DEFAULT_LANG,
            )
            await self.coordinator.async_request_refresh()

        except WattsApiError as err:
            _LOGGER.error(
                "Failed to set %s for device %s: %s",
                self.entity_description.field,
                self._device_id,
                err,
            )
