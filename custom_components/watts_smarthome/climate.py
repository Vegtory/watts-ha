"""Climate (thermostat) entities for Watts SmartHome."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_TENTHS, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import WattsConfigEntry
from .const import (
    ANTI_FROST_MAX_C,
    ANTI_FROST_MIN_C,
    MODE_ANTI_FROST,
    MODE_BOOST,
    MODE_COMFORT,
    MODE_ECO,
    MODE_OFF,
    MODE_PROGRAM_ON,
    TEMPERATURE_STEP_C,
)
from .entity import WattsScheduleAwareEntity, async_setup_device_entities

# Writes are queued and merged by the coordinator.
PARALLEL_UPDATES = 0

PRESET_MODES = [MODE_COMFORT, MODE_ECO, MODE_ANTI_FROST, MODE_BOOST]
DEFAULT_MIN_TEMP = 5.0
DEFAULT_MAX_TEMP = 37.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WattsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts thermostats from a config entry."""
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, smarthome_id, id_device: [
            WattsClimate(coordinator=coordinator, smarthome_id=smarthome_id, id_device=id_device)
        ],
    )


class WattsClimate(WattsScheduleAwareEntity, ClimateEntity):
    """A Watts thermostat.

    HVAC modes: AUTO = weekly schedule, HEAT = fixed preset, OFF.
    Presets (in HEAT): comfort, eco, anti-frost, boost.

    In AUTO there is no target temperature (Home Assistant convention, and the
    Watts app does not allow it either): the schedule switches between the
    comfort and eco setpoints. The active period and its temperature are shown
    as attributes. Switch to HEAT to set a temperature.
    """

    _attr_name = None
    _attr_translation_key = "thermostat"
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = PRESET_MODES
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMPERATURE_STEP_C
    _attr_precision = PRECISION_TENTHS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, *, coordinator, smarthome_id: str, id_device: str) -> None:
        super().__init__(
            coordinator=coordinator,
            smarthome_id=smarthome_id,
            id_device=id_device,
            entity_key="climate",
        )

    @property
    def hvac_mode(self) -> HVACMode:
        device = self.device
        if device.is_off:
            return HVACMode.OFF
        if device.is_program:
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        device = self.device
        if device.is_off:
            return HVACAction.OFF
        return HVACAction.HEATING if device.heating_up else HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        mode = self.device.current_mode
        return mode if mode in PRESET_MODES else None

    @property
    def current_temperature(self) -> float | None:
        return self.device.current_air_temperature

    @property
    def target_temperature(self) -> float | None:
        device = self.device
        if device.is_program or device.is_off:
            return None
        return device.target_temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        device = self.device
        if not device.is_program:
            return None
        period, change = device.schedule_now(dt_util.now())
        if device.is_boost:
            period = MODE_BOOST
        return {
            "schedule_period": period,
            "schedule_temperature": device.schedule_temperature(period),
            "next_change": change.at.isoformat() if change else None,
            "next_period": change.period if change else None,
            "next_temperature": device.schedule_temperature(change.period) if change else None,
        }

    @property
    def min_temp(self) -> float:
        if self.device.current_mode == MODE_ANTI_FROST:
            return ANTI_FROST_MIN_C
        return self.device.min_set_point or DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        if self.device.current_mode == MODE_ANTI_FROST:
            return ANTI_FROST_MAX_C
        return self.device.max_set_point or DEFAULT_MAX_TEMP

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == self.hvac_mode:
            return
        if hvac_mode == HVACMode.OFF:
            mode = MODE_OFF
        elif hvac_mode == HVACMode.AUTO:
            mode = MODE_PROGRAM_ON
        else:
            mode = MODE_COMFORT
        await self.coordinator.async_set_mode(self._smarthome_id, self._id_device, mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self.coordinator.async_set_mode(self._smarthome_id, self._id_device, preset_mode)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(hvac_mode)
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_set_target_temperature(self._smarthome_id, self._id_device, temperature)

    async def async_turn_on(self) -> None:
        """Turn on by resuming the weekly schedule."""
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
