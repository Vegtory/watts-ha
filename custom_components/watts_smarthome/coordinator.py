"""Data update coordinator for Watts SmartHome."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
import logging
import time

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntryAuthFailed

from .api import WattsApiClient, WattsApiError, WattsAuthError, WattsConnectionError
from .const import POST_WRITE_FAST_POLL_DURATION_SECONDS, POST_WRITE_FAST_POLL_INTERVAL_SECONDS
from .models import (
    WattsDevice,
    WattsState,
    WattsWriteRequest,
    build_boost_timer_write_request,
    build_mode_write_request,
    build_setpoint_write_request,
    parse_state,
)

_LOGGER = logging.getLogger(__name__)


class WattsDataUpdateCoordinator(DataUpdateCoordinator[WattsState]):
    """Coordinates reading and writing Watts device state."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        client: WattsApiClient,
        lang: str,
        scan_interval_seconds: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Watts SmartHome",
            update_interval=timedelta(seconds=scan_interval_seconds),
        )
        self.client = client
        self.lang = lang
        self._normal_update_interval = timedelta(seconds=scan_interval_seconds)
        self._fast_update_interval = timedelta(
            seconds=min(scan_interval_seconds, POST_WRITE_FAST_POLL_INTERVAL_SECONDS)
        )
        self._fast_poll_until: float | None = None
        self._refresh_poll_mode()

    async def _async_update_data(self) -> WattsState:
        """Fetch all data from Watts and map it into domain models."""
        self._refresh_poll_mode()
        try:
            user_payload = await self.client.async_get_user_data(lang=self.lang)

            smarthome_ids = [
                str(smarthome.get("smarthome_id", "")).strip()
                for smarthome in (user_payload.get("data") or {}).get("smarthomes", [])
                if str(smarthome.get("smarthome_id", "")).strip()
            ]

            async def load_smarthome(smarthome_id: str) -> tuple[str, dict, dict]:
                read_payload = await self.client.async_get_smarthome_data(smarthome_id, lang=self.lang)
                try:
                    error_payload = await self.client.async_get_errors(smarthome_id, lang=self.lang)
                except WattsApiError as err:
                    _LOGGER.debug("Ignoring get_errors failure for %s: %s", smarthome_id, err)
                    error_payload = {}
                return smarthome_id, read_payload, error_payload

            smarthome_payloads: dict[str, dict] = {}
            smarthome_error_payloads: dict[str, dict] = {}
            if smarthome_ids:
                results = await asyncio.gather(*(load_smarthome(smarthome_id) for smarthome_id in smarthome_ids))
                for smarthome_id, smarthome_payload, error_payload in results:
                    smarthome_payloads[smarthome_id] = smarthome_payload
                    smarthome_error_payloads[smarthome_id] = error_payload

            return parse_state(
                user_payload=user_payload,
                smarthome_payloads=smarthome_payloads,
                smarthome_error_payloads=smarthome_error_payloads,
            )

        except WattsAuthError as err:
            raise ConfigEntryAuthFailed from err
        except WattsConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except WattsApiError as err:
            raise UpdateFailed(str(err)) from err
        finally:
            self._refresh_poll_mode()

    def get_device(self, smarthome_id: str, id_device: str) -> WattsDevice:
        """Return one device from coordinator state."""
        if self.data is None:
            raise HomeAssistantError("Watts coordinator has no data")
        return self.data.get_device(smarthome_id, id_device)

    def device_keys(self) -> set[tuple[str, str]]:
        """Return all known `(smarthome_id, id_device)` keys."""
        if self.data is None:
            return set()

        keys: set[tuple[str, str]] = set()
        for home in self.data.smarthomes:
            for device in home.devices:
                keys.add((home.smarthome_id, device.id_device))
        return keys

    async def async_set_mode(self, smarthome_id: str, id_device: str, mode_option: str) -> None:
        """Set operating mode for a device."""
        device = self.get_device(smarthome_id, id_device)
        request = build_mode_write_request(device=device, selected_mode=mode_option)
        await self._async_execute_write(request)

    async def async_set_setpoint(
        self,
        smarthome_id: str,
        id_device: str,
        setpoint_key: str,
        value_celsius: float,
    ) -> None:
        """Set one mode setpoint for a device."""
        device = self.get_device(smarthome_id, id_device)
        request = build_setpoint_write_request(
            device=device,
            setpoint_key=setpoint_key,
            value_celsius=value_celsius,
        )
        await self._async_execute_write(request)

    async def async_set_boost_timer(self, smarthome_id: str, id_device: str, value_seconds: int) -> None:
        """Set boost timer duration for a device."""
        device = self.get_device(smarthome_id, id_device)
        request = build_boost_timer_write_request(device=device, value_seconds=value_seconds)
        await self._async_execute_write(request)

    async def _async_execute_write(self, request: WattsWriteRequest) -> None:
        """Execute a write command and refresh coordinator."""

        async def _do_push() -> None:
            await self.client.async_push_query(
                request.smarthome_id,
                request.query,
                lang=self.lang,
            )

        await self._wrap_write(_do_push)
        self._enable_fast_poll_window()
        await self.async_request_refresh()

    async def _wrap_write(self, action: Callable[[], Awaitable[None]]) -> None:
        """Normalize write errors to Home Assistant exceptions."""
        try:
            await action()
        except WattsAuthError as err:
            raise ConfigEntryAuthFailed from err
        except (WattsConnectionError, WattsApiError) as err:
            raise HomeAssistantError(str(err)) from err

    def _enable_fast_poll_window(self) -> None:
        """Enable temporary fast polling after a write."""
        self._fast_poll_until = time.monotonic() + POST_WRITE_FAST_POLL_DURATION_SECONDS
        self._refresh_poll_mode()

    def _refresh_poll_mode(self) -> None:
        """Switch poll interval between normal and temporary fast mode."""
        now = time.monotonic()
        fast_mode_active = (
            self._fast_poll_until is not None
            and now < self._fast_poll_until
            and self._fast_update_interval < self._normal_update_interval
        )

        target_interval = self._fast_update_interval if fast_mode_active else self._normal_update_interval
        if not fast_mode_active:
            self._fast_poll_until = None

        if self.update_interval != target_interval:
            self.update_interval = target_interval
            _LOGGER.debug("Set Watts polling interval to %s", target_interval)
