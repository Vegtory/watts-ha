"""Select platform for Watts SmartHome."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    MODE_CODE_TO_OPTION,
    MODE_OPTION_TO_CODE,
)
from .entity import WattsDeviceEntity
from . import WattsRuntimeData

_LOGGER = logging.getLogger(__name__)

MODE_OPTIONS = list(MODE_OPTION_TO_CODE)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Watts mode select entities."""
    runtime: WattsRuntimeData = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator

    entities: list[WattsModeSelect] = []
    for smarthome_id, device_id in coordinator.iter_device_keys():
        entities.append(
            WattsModeSelect(
                coordinator=coordinator,
                smarthome_id=smarthome_id,
                device_id=device_id,
            )
        )

    async_add_entities(entities)


class WattsModeSelect(WattsDeviceEntity, SelectEntity):
    """Select entity for device operating mode."""

    _attr_options = MODE_OPTIONS
    _attr_icon = "mdi:cached"

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
            "mode",
            entity_name="Mode",
        )

    @property
    def current_option(self) -> str | None:
        device = self._device
        if device is None:
            return None
        mode_code = str(device.get("gv_mode", ""))
        return MODE_CODE_TO_OPTION.get(mode_code, MODE_OPTIONS[0])

    async def async_select_option(self, option: str) -> None:
        if option not in MODE_OPTION_TO_CODE:
            raise ValueError(f"Unsupported Watts mode option: {option}")
        mode_code = MODE_OPTION_TO_CODE[option]
        updates = {"gv_mode": mode_code, "nv_mode": mode_code}

        device = self._device
        if device and option == "Boost":
            # Match observed webapp payload for boost requests.
            boost_setpoint = device.get("consigne_boost")
            boost_time = device.get("time_boost")
            if boost_time is not None:
                updates["time_boost"] = str(boost_time)
            if boost_setpoint is not None:
                updates["consigne_boost"] = str(boost_setpoint)
                updates["consigne_manuel"] = str(boost_setpoint)

        first_attempt = await self.coordinator.async_push_device_update(
            self._smarthome_id,
            self._device_id,
            updates,
        )

        device = self._device
        if device is None:
            return

        current_mode = str(device.get("gv_mode", ""))
        if current_mode == mode_code:
            return

        device = self._device
        if device and str(device.get("gv_mode", "")) != mode_code:
            check_failure = await self.coordinator.async_check_query_failure(self._smarthome_id)
            _LOGGER.warning(
                "Watts mode change not reflected for %s#%s target=%s current=%s "
                "first_attempt=%s check_failure=%s",
                self._smarthome_id,
                self._device_id,
                mode_code,
                device.get("gv_mode"),
                self._summarize_attempts(first_attempt),
                self._summarize_check_failure(check_failure),
            )

    @staticmethod
    def _summarize_attempts(result: dict[str, Any] | None) -> str:
        """Return compact mode push attempt summary for logs."""
        if not result:
            return "none"
        attempts = result.get("attempts")
        if not isinstance(attempts, list):
            return "invalid"
        parts: list[str] = []
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            strategy = str(attempt.get("strategy", "?"))
            query = attempt.get("query", {})
            if isinstance(query, dict):
                mode_query = {
                    "gv_mode": query.get("gv_mode"),
                    "nv_mode": query.get("nv_mode"),
                    "id_device": query.get("id_device"),
                }
            else:
                mode_query = {"query": "invalid"}

            if "error" in attempt:
                parts.append(f"{strategy}:error={attempt.get('error')} query={mode_query}")
            else:
                parts.append(
                    f"{strategy}:code={attempt.get('code')} key={attempt.get('key')} "
                    f"value={attempt.get('value')} query={mode_query}"
                )
        return " | ".join(parts) if parts else "empty"

    @staticmethod
    def _summarize_check_failure(payload: dict[str, Any]) -> str:
        """Return compact check_failure summary for logs."""
        if not isinstance(payload, dict):
            return "invalid"
        if "error" in payload:
            return f"error={payload['error']}"
        code = payload.get("code")
        if isinstance(code, dict):
            return (
                f"code={code.get('code')} key={code.get('key')} value={code.get('value')} "
                f"data={payload.get('data')}"
            )
        return str(payload)
