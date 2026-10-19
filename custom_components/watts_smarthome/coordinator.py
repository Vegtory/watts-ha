"""Data update coordinator for Watts SmartHome.

Reads
-----
One refresh loads, per smarthome, `smarthome/read`, `smarthome/get_errors` and
`sandbox/check_last_connexion`. `user/read` (the smarthome list) is reloaded only
every USER_REFRESH_INTERVAL_SECONDS.

Writes (same protocol as the official web app)
----------------------------------------------
1. Quick successive writes to one device are merged into one push
   (WRITE_DEBOUNCE_SECONDS). The new state shows in Home Assistant at once.
2. Before pushing, the central unit must have checked in within
   MAX_CENTRAL_SILENCE_SECONDS, otherwise the command is refused.
3. `query/push` queues the command in the cloud for `peremption` ms.
4. No reads for POST_WRITE_QUIET_SECONDS: the cloud still returns old values then.
5. After the peremption window, `query/check_failure` tells whether the command
   expired undelivered. On failure the next peremption is longer (15 -> 30 s) and
   the optimistic state is dropped.
6. Refreshes continue every CONFIRM_RETRY_INTERVAL_SECONDS until `smarthome/read`
   shows the new values, or CONFIRM_TIMEOUT_SECONDS passes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
import time
from typing import TYPE_CHECKING, Any, Literal

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import WattsApiClient, WattsApiError, WattsAuthError, WattsConnectionError, WattsError
from .const import (
    CHECK_FAILURE_MARGIN_SECONDS,
    CONFIRM_RETRY_INTERVAL_SECONDS,
    CONFIRM_TIMEOUT_SECONDS,
    CONNECTION_CHECK_CACHE_SECONDS,
    DEFAULT_BOOST_SECONDS,
    DOMAIN,
    FIELD_ID_DEVICE,
    MAX_CENTRAL_SILENCE_SECONDS,
    MODE_LABELS,
    PEREMPTION_STEPS_MS,
    POST_WRITE_QUIET_SECONDS,
    SETPOINT_KEYS,
    SETPOINT_LABELS,
    SETPOINT_MANUAL,
    USER_REFRESH_INTERVAL_SECONDS,
    WRITE_DEBOUNCE_SECONDS,
)
from .models import (
    TRACKED_WRITE_FIELDS,
    WattsDevice,
    WattsSmarthome,
    WattsState,
    WattsWriteRequest,
    build_boost_write_request,
    build_mode_write_request,
    build_setpoint_write_request,
    merge_queries,
    mode_from_code,
    parse_state,
    raw_to_celsius,
)

if TYPE_CHECKING:
    from . import WattsConfigEntry

_LOGGER = logging.getLogger(__name__)

DeviceKey = tuple[str, str]
CommandStatus = Literal["idle", "sending", "sent", "delivered", "failed"]

# Pending optimistic state lives this long when a push never happens (safety net).
_UNSENT_PENDING_SECONDS = 60.0


@dataclass(slots=True)
class _PendingState:
    """Optimistic fields shown until smarthome/read confirms them."""

    fields: dict[str, str]
    expect: dict[str, str]
    deadline: float


@dataclass(slots=True)
class _QueuedWrite:
    """A debounced command waiting to be pushed."""

    query: dict[str, str]
    waiters: list[asyncio.Future[None]] = field(default_factory=list)
    handle: asyncio.TimerHandle | None = None


@dataclass(slots=True)
class SmarthomeSyncState:
    """Command sync bookkeeping for one smarthome."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    peremption_index: int = 0
    quiet_until: float = 0.0
    connection_checked_at: float | None = None
    seconds_since_contact: int | None = None
    verify_task: asyncio.Task[None] | None = None
    verify_due: float = 0.0
    status: CommandStatus = "idle"
    last_push_at: float | None = None
    last_failure: dict[str, Any] | None = None

    @property
    def peremption_ms(self) -> int:
        return PEREMPTION_STEPS_MS[self.peremption_index]


class WattsDataUpdateCoordinator(DataUpdateCoordinator[WattsState]):
    """Coordinates reading and writing Watts device state."""

    config_entry: WattsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WattsConfigEntry,
        *,
        client: WattsApiClient,
        lang: str,
        scan_interval_seconds: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval_seconds),
            # Entities only re-render when something changed.
            always_update=False,
        )
        self.client = client
        self.lang = lang
        self._cloud_state: WattsState | None = None
        self._user_payload: dict[str, Any] | None = None
        self._user_fetched_at: float = 0.0
        self._pending: dict[DeviceKey, _PendingState] = {}
        self._queued: dict[DeviceKey, _QueuedWrite] = {}
        self._sync: dict[str, SmarthomeSyncState] = {}
        # Boost duration chosen in Home Assistant, per device (the cloud has no such setting).
        self.boost_seconds: dict[DeviceKey, int] = {}

    # --- Reads ----------------------------------------------------------------------

    def sync_state(self, smarthome_id: str) -> SmarthomeSyncState:
        """Return (and create) sync bookkeeping for a smarthome."""
        return self._sync.setdefault(smarthome_id, SmarthomeSyncState())

    def _in_quiet_window(self) -> bool:
        now = time.monotonic()
        return any(sync.quiet_until > now for sync in self._sync.values())

    async def _async_update_data(self) -> WattsState:
        """Fetch all data from Watts and map it into domain models."""
        if self._cloud_state is not None and self._in_quiet_window():
            # Reading now would return pre-command values; keep the current view.
            _LOGGER.debug("Skipping refresh inside post-write quiet window")
            return self._build_view()

        try:
            user_payload = await self._async_get_user_payload()
            smarthome_ids = [
                str(home.get("smarthome_id", "")).strip()
                for home in (user_payload.get("data") or {}).get("smarthomes") or []
                if str(home.get("smarthome_id", "")).strip()
            ]
            results = await asyncio.gather(*(self._async_load_smarthome(sid) for sid in smarthome_ids))
        except WattsAuthError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="auth_failed") from err
        except WattsError as err:
            raise UpdateFailed(f"Error talking to Watts cloud: {err}") from err

        self._cloud_state = parse_state(
            user_payload=user_payload,
            smarthome_payloads={sid: read for sid, read, _, _ in results},
            smarthome_error_payloads={sid: errors for sid, _, errors, _ in results},
            connection_seconds={sid: seconds for sid, _, _, seconds in results},
        )
        self._reconcile_pending()
        return self._build_view()

    async def _async_get_user_payload(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._user_payload is None or now - self._user_fetched_at >= USER_REFRESH_INTERVAL_SECONDS:
            self._user_payload = await self.client.async_get_user_data(lang=self.lang)
            self._user_fetched_at = now
        return self._user_payload

    async def _async_load_smarthome(self, smarthome_id: str) -> tuple[str, dict[str, Any], dict[str, Any], int | None]:
        read_payload, error_payload, connection = await asyncio.gather(
            self.client.async_get_smarthome_data(smarthome_id, lang=self.lang),
            self.client.async_get_errors(smarthome_id, lang=self.lang),
            self.client.async_check_last_connection(smarthome_id, lang=self.lang),
            return_exceptions=True,
        )
        if isinstance(read_payload, BaseException):
            raise read_payload
        if isinstance(error_payload, BaseException):
            if isinstance(error_payload, WattsAuthError):
                raise error_payload
            _LOGGER.debug("Ignoring get_errors failure for %s: %s", smarthome_id, error_payload)
            error_payload = {}

        seconds: int | None = None
        if isinstance(connection, BaseException):
            if isinstance(connection, WattsAuthError):
                raise connection
            _LOGGER.debug("Ignoring check_last_connexion failure for %s: %s", smarthome_id, connection)
            seconds = self.sync_state(smarthome_id).seconds_since_contact
        else:
            seconds = connection.seconds_since_contact
            sync = self.sync_state(smarthome_id)
            sync.seconds_since_contact = seconds
            sync.connection_checked_at = time.monotonic()

        return smarthome_id, read_payload, error_payload, seconds

    # --- Optimistic view ------------------------------------------------------------

    def _reconcile_pending(self) -> None:
        """Drop optimistic fields the cloud now confirms, or that timed out."""
        if self._cloud_state is None:
            return
        now = time.monotonic()
        for key in list(self._pending):
            pending = self._pending[key]
            device = self._cloud_state.get_device(*key)
            if device is None:
                del self._pending[key]
                continue
            if all(device.raw_field(name) == value for name, value in pending.expect.items()):
                _LOGGER.debug("Watts state for %s confirmed: %s", key, pending.expect)
                del self._pending[key]
                sync = self.sync_state(key[0])
                if sync.status == "sent":
                    sync.status = "delivered"
                    self._dismiss_not_applied(key[0])
            elif now >= pending.deadline:
                _LOGGER.warning(
                    "Watts device %s did not report the requested values %s within the expected time",
                    key[1],
                    pending.expect,
                )
                self._notify_not_applied(
                    key[0],
                    [self._describe_change(key, pending.fields)],
                    "The Watts cloud accepted the change, but the thermostat still reports its old settings.",
                )
                del self._pending[key]

    def _build_view(self) -> WattsState:
        """Return cloud state with optimistic (pending) fields applied."""
        assert self._cloud_state is not None
        if not self._pending:
            return self._cloud_state

        homes: list[WattsSmarthome] = []
        for home in self._cloud_state.smarthomes:
            devices = tuple(
                device.with_raw_fields(pending.fields)
                if (pending := self._pending.get((home.smarthome_id, device.id_device)))
                else device
                for device in home.devices
            )
            homes.append(home.with_devices(devices))
        return WattsState(user=self._cloud_state.user, smarthomes=tuple(homes))

    @callback
    def _publish_view(self) -> None:
        if self._cloud_state is not None:
            self.async_set_updated_data(self._build_view())

    def has_pending(self, smarthome_id: str) -> bool:
        """Return True while optimistic state for a smarthome is unconfirmed."""
        return any(key[0] == smarthome_id for key in (*self._pending, *self._queued))

    # --- Lookups --------------------------------------------------------------------

    def get_device(self, smarthome_id: str, id_device: str) -> WattsDevice | None:
        """Return one device (with optimistic state) or None when gone."""
        if self.data is None:
            return None
        return self.data.get_device(smarthome_id, id_device)

    def get_smarthome(self, smarthome_id: str) -> WattsSmarthome | None:
        """Return one smarthome or None when gone."""
        if self.data is None:
            return None
        return self.data.get_smarthome(smarthome_id)

    def device_keys(self) -> set[DeviceKey]:
        """Return all known `(smarthome_id, id_device)` keys."""
        if self.data is None:
            return set()
        return {(home.smarthome_id, device.id_device) for home in self.data.smarthomes for device in home.devices}

    def smarthome_ids(self) -> set[str]:
        """Return all known smarthome ids."""
        if self.data is None:
            return set()
        return {home.smarthome_id for home in self.data.smarthomes}

    def _require_device(self, smarthome_id: str, id_device: str) -> WattsDevice:
        device = self.get_device(smarthome_id, id_device)
        if device is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_not_found")
        return device

    def get_boost_seconds(self, smarthome_id: str, id_device: str) -> int:
        """Return the boost duration to use when starting boost."""
        if (seconds := self.boost_seconds.get((smarthome_id, id_device))) is not None:
            return seconds
        device = self.get_device(smarthome_id, id_device)
        return (device.time_boost_seconds if device else 0) or DEFAULT_BOOST_SECONDS

    # --- Write API (used by entities) ---------------------------------------------

    async def async_set_mode(
        self, smarthome_id: str, id_device: str, mode_option: str, *, boost_seconds: int | None = None
    ) -> None:
        """Switch a device to another operating mode."""
        device = self._require_device(smarthome_id, id_device)
        if boost_seconds is None:
            boost_seconds = self.get_boost_seconds(smarthome_id, id_device)
        try:
            request = build_mode_write_request(device=device, selected_mode=mode_option, boost_seconds=boost_seconds)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_mode",
                translation_placeholders={"mode": mode_option},
            ) from err
        await self._async_queue_write(request)

    async def async_set_setpoint(
        self, smarthome_id: str, id_device: str, setpoint_key: str, value_celsius: float
    ) -> None:
        """Change one setpoint, keeping the current mode."""
        device = self._require_device(smarthome_id, id_device)
        request = build_setpoint_write_request(device=device, setpoint_key=setpoint_key, value_celsius=value_celsius)
        await self._async_queue_write(request)

    async def async_set_target_temperature(self, smarthome_id: str, id_device: str, value_celsius: float) -> None:
        """Change the setpoint the current mode uses."""
        device = self._require_device(smarthome_id, id_device)
        if device.is_program:
            # The schedule switches between the comfort and eco setpoints; changing one here
            # would silently change every period of the week (the Watts app does not allow it).
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="target_in_schedule")
        key = device.active_setpoint_key
        if key is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_target_in_mode")
        await self.async_set_setpoint(smarthome_id, id_device, key, value_celsius)

    async def async_set_boost_duration(self, smarthome_id: str, id_device: str, boost_seconds: int) -> None:
        """Restart a running boost with a new duration."""
        device = self._require_device(smarthome_id, id_device)
        await self._async_queue_write(build_boost_write_request(device=device, boost_seconds=boost_seconds))

    # --- Write pipeline -----------------------------------------------------------------

    def _check_writable(self, smarthome_id: str) -> None:
        home = self.get_smarthome(smarthome_id)
        if home is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_not_found")
        if home.holiday_active(dt_util.now().replace(tzinfo=None)):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="holiday_mode")

    async def _async_queue_write(self, request: WattsWriteRequest) -> None:
        """Show the change at once, then push it (merged with other quick writes)."""
        self._check_writable(request.smarthome_id)
        key: DeviceKey = (request.smarthome_id, request.id_device)
        changes = {name: value for name, value in request.query.items() if name != FIELD_ID_DEVICE}

        # Optimistic state, so a follow-up write builds on the new values.
        self._add_pending(key, changes, deadline=time.monotonic() + _UNSENT_PENDING_SECONDS)

        queued = self._queued.get(key)
        if queued is None:
            queued = self._queued[key] = _QueuedWrite(query=dict(request.query))
        else:
            queued.query = merge_queries(queued.query, request.query)
            if queued.handle is not None:
                queued.handle.cancel()

        waiter: asyncio.Future[None] = self.hass.loop.create_future()
        queued.waiters.append(waiter)
        queued.handle = self.hass.loop.call_later(WRITE_DEBOUNCE_SECONDS, self._schedule_flush, key)
        self._publish_view()
        await waiter

    def _add_pending(self, key: DeviceKey, changes: dict[str, str], *, deadline: float) -> None:
        expect = {name: value for name, value in changes.items() if name in TRACKED_WRITE_FIELDS}
        if changes.get("gv_mode") == "15" and SETPOINT_MANUAL in changes:
            expect[SETPOINT_MANUAL] = changes[SETPOINT_MANUAL]
        pending = self._pending.get(key)
        if pending is None:
            self._pending[key] = _PendingState(fields=dict(changes), expect=expect, deadline=deadline)
        else:
            pending.fields.update(changes)
            pending.expect.update(expect)
            pending.deadline = max(pending.deadline, deadline)

    @callback
    def _schedule_flush(self, key: DeviceKey) -> None:
        self.config_entry.async_create_background_task(
            self.hass, self._async_flush(key), name=f"{DOMAIN} push {key[1]}"
        )

    async def _async_flush(self, key: DeviceKey) -> None:
        queued = self._queued.pop(key, None)
        if queued is None:
            return
        smarthome_id = key[0]
        sync = self.sync_state(smarthome_id)
        error: BaseException | None = None

        async with sync.lock:
            try:
                await self._async_ensure_central_online(smarthome_id)
                sync.status = "sending"
                peremption_ms = sync.peremption_ms
                _LOGGER.debug("Pushing %s (peremption %s ms)", queued.query, peremption_ms)
                await self.client.async_push_query(
                    smarthome_id, queued.query, lang=self.lang, peremption_ms=peremption_ms
                )
            except WattsAuthError as err:
                error = HomeAssistantError(translation_domain=DOMAIN, translation_key="auth_failed")
                error.__cause__ = err
                self.config_entry.async_start_reauth(self.hass)
            except (WattsConnectionError, WattsApiError) as err:
                error = HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="command_failed",
                    translation_placeholders={"error": str(err)},
                )
                error.__cause__ = err
            except HomeAssistantError as err:
                error = err
            else:
                now = time.monotonic()
                sync.status = "sent"
                sync.last_push_at = now
                sync.quiet_until = now + POST_WRITE_QUIET_SECONDS
                window = peremption_ms / 1000 + CHECK_FAILURE_MARGIN_SECONDS
                if (pending := self._pending.get(key)) is not None:
                    pending.deadline = now + window + CONFIRM_TIMEOUT_SECONDS
                self._start_verify(smarthome_id, delay=window)

        if error is not None:
            sync.status = "failed"
            self._pending.pop(key, None)
            self._publish_view()
        else:
            self.async_update_listeners()
        for waiter in queued.waiters:
            if waiter.done():
                continue
            if error is None:
                waiter.set_result(None)
            else:
                waiter.set_exception(error)

    async def _async_ensure_central_online(self, smarthome_id: str) -> None:
        """Refuse to push when the central unit has stopped checking in."""
        sync = self.sync_state(smarthome_id)
        now = time.monotonic()
        if sync.connection_checked_at is None or now - sync.connection_checked_at > CONNECTION_CHECK_CACHE_SECONDS:
            status = await self.client.async_check_last_connection(smarthome_id, lang=self.lang)
            sync.seconds_since_contact = status.seconds_since_contact
            sync.connection_checked_at = time.monotonic()

        seconds = sync.seconds_since_contact
        if seconds is None or seconds > MAX_CENTRAL_SILENCE_SECONDS:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="central_offline",
                translation_placeholders={"seconds": "never" if seconds is None else str(seconds)},
            )

    def _start_verify(self, smarthome_id: str, *, delay: float) -> None:
        """Schedule the result check; a newer push moves it later (check_failure covers all)."""
        sync = self.sync_state(smarthome_id)
        sync.verify_due = time.monotonic() + delay
        if sync.verify_task is None or sync.verify_task.done():
            sync.verify_task = self.config_entry.async_create_background_task(
                self.hass, self._async_verify(smarthome_id), name=f"{DOMAIN} verify {smarthome_id}"
            )

    async def _async_verify(self, smarthome_id: str) -> None:
        """Check command results after their window, then refresh until confirmed."""
        sync = self.sync_state(smarthome_id)
        while True:
            while (wait := sync.verify_due - time.monotonic()) > 0:
                await asyncio.sleep(wait)
            handled_due = sync.verify_due

            await self._async_check_failure(smarthome_id, sync)
            sync.quiet_until = 0.0
            self.async_update_listeners()
            await self.async_refresh()

            while sync.verify_due == handled_due and self.has_pending(smarthome_id):
                await asyncio.sleep(CONFIRM_RETRY_INTERVAL_SECONDS)
                if sync.verify_due == handled_due:
                    await self.async_refresh()

            if sync.verify_due == handled_due:
                return
            # Another command was pushed meanwhile: wait for its window too.

    async def _async_check_failure(self, smarthome_id: str, sync: SmarthomeSyncState) -> None:
        try:
            result = await self.client.async_check_query_failure(smarthome_id, lang=self.lang)
        except WattsError as err:
            # Unknown outcome: the status stays "sent" until a read confirms the values.
            _LOGGER.debug("check_failure for %s failed: %s", smarthome_id, err)
            return

        if not result.failed:
            sync.status = "delivered"
            sync.peremption_index = 0
            self._dismiss_not_applied(smarthome_id)
            return

        sync.status = "failed"
        sync.last_failure = result.details
        sync.peremption_index = min(sync.peremption_index + 1, len(PEREMPTION_STEPS_MS) - 1)
        _LOGGER.warning(
            "Watts central unit %s did not pick up a command in time; next commands will wait %s s",
            smarthome_id,
            sync.peremption_ms / 1000,
        )
        failed_keys = [key for key in self._pending if key[0] == smarthome_id]
        self._notify_not_applied(
            smarthome_id,
            [self._describe_change(key, self._pending[key].fields) for key in failed_keys],
            "The central unit did not pick up the change in time, so the thermostat keeps its previous "
            "settings. Try again; the next change waits longer for the central unit.",
        )
        for key in failed_keys:
            del self._pending[key]

    # --- User notifications -----------------------------------------------------------

    def _describe_change(self, key: DeviceKey, fields: dict[str, str]) -> str:
        """Return e.g. 'Bedroom: mode Comfort, comfort temperature 21.0 °C'."""
        device = self._cloud_state.get_device(*key) if self._cloud_state else None
        name = device.display_name if device else key[1]
        parts: list[str] = []
        if (code := fields.get("gv_mode")) is not None:
            mode = mode_from_code(code)
            parts.append(f"mode {MODE_LABELS.get(mode, mode)}")
        for setpoint in SETPOINT_KEYS:
            if (raw := fields.get(setpoint)) is not None and (celsius := raw_to_celsius(raw)) is not None:
                parts.append(f"{SETPOINT_LABELS[setpoint]} {celsius:.1f} °C")
        return f"{name}: {', '.join(parts) or 'settings'}"

    def _notification_id(self, smarthome_id: str) -> str:
        return f"{DOMAIN}_{self.config_entry.entry_id}_{smarthome_id}_command"

    @callback
    def _notify_not_applied(self, smarthome_id: str, changes: list[str], reason: str) -> None:
        if not changes:
            return
        lines = "\n".join(f"- {change}" for change in changes)
        persistent_notification.async_create(
            self.hass,
            f"{reason}\n\n{lines}",
            title="Watts SmartHome: change not applied",
            notification_id=self._notification_id(smarthome_id),
        )

    @callback
    def _dismiss_not_applied(self, smarthome_id: str) -> None:
        persistent_notification.async_dismiss(self.hass, self._notification_id(smarthome_id))

    async def async_shutdown(self) -> None:
        """Cancel timers and background work."""
        for queued in self._queued.values():
            if queued.handle is not None:
                queued.handle.cancel()
            for waiter in queued.waiters:
                if not waiter.done():
                    waiter.cancel()
        self._queued.clear()
        for sync in self._sync.values():
            if sync.verify_task is not None:
                sync.verify_task.cancel()
        await super().async_shutdown()
