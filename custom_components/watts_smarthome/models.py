"""Domain models and mappers for Watts SmartHome."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from .const import (
    BOOST_TIMER,
    CELSIUS_TO_FAHRENHEIT_FACTOR,
    DEFAULT_BOOST_SECONDS,
    FAHRENHEIT_OFFSET,
    FAHRENHEIT_TO_CELSIUS_FACTOR,
    FIELD_GV_MODE,
    FIELD_ID_DEVICE,
    FIELD_NV_MODE,
    FIELD_PROGRAMME,
    HEATING_ACTIVE,
    HEATING_IDLE,
    MAX_BOOST_SECONDS,
    MIN_BOOST_SECONDS,
    MODE_BOOST,
    MODE_CODE_TO_OPTION,
    MODE_COMFORT,
    MODE_ECO,
    MODE_OFF,
    MODE_OPTION_TO_CODE,
    MODE_PROGRAM_BOOST,
    MODE_PROGRAM_ON,
    MODE_UNKNOWN,
    PROGRAM_MODES,
    RAW_TEMPERATURE_DECI_SCALE,
    SELECTABLE_MODES,
    SETPOINT_BY_MODE,
    SETPOINT_COMFORT,
    SETPOINT_KEYS,
    SETPOINT_MANUAL,
    TEMPERATURE_STEP_C,
    VALID_TEMPERATURE_MAX_C,
    VALID_TEMPERATURE_MIN_C,
)

# Holiday dates the app treats as "not set".
_UNSET_HOLIDAY_DATES = {"", "null", "0000-00-00 00:00:00", "1970-01-01 00:00:00", "2014-01-01 00:00:00"}
_HOLIDAY_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Raw fields we expect smarthome/read to echo back after a successful write.
TRACKED_WRITE_FIELDS: frozenset[str] = frozenset({FIELD_GV_MODE, FIELD_PROGRAMME, *SETPOINT_KEYS})


def _as_str(value: Any) -> str:
    """Return value as trimmed string."""
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any) -> int | None:
    """Return value as int when possible."""
    text = _as_str(value)
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def raw_to_celsius(raw_value: str | int | None) -> float | None:
    """Convert a Watts raw (deci-Fahrenheit) temperature to Celsius.

    Returns None for values the app shows as "--.-" (no sensor).
    """
    raw_int = _as_int(raw_value)
    if raw_int is None:
        return None
    celsius = (raw_int / RAW_TEMPERATURE_DECI_SCALE - FAHRENHEIT_OFFSET) * FAHRENHEIT_TO_CELSIUS_FACTOR
    if not VALID_TEMPERATURE_MIN_C < celsius < VALID_TEMPERATURE_MAX_C:
        return None
    return round(celsius, 1)


def celsius_to_raw(temperature: float) -> int:
    """Convert a Celsius value to Watts raw (deci-Fahrenheit) temperature."""
    fahrenheit_value = (temperature * CELSIUS_TO_FAHRENHEIT_FACTOR) + FAHRENHEIT_OFFSET
    return round(fahrenheit_value * RAW_TEMPERATURE_DECI_SCALE)


def round_to_step(celsius: float) -> float:
    """Round to the 0.5 °C steps the thermostats accept."""
    return round(celsius / TEMPERATURE_STEP_C) * TEMPERATURE_STEP_C


# --- Weekly schedule ("programme") ------------------------------------------------
# 336 hex characters: Monday first, one character per 30 minutes, two bits per
# 15 minutes (high bits = first quarter). 0 = eco, 1 = comfort. Verified against
# the app's sandbox/convert_program output.
SCHEDULE_SLOT_MINUTES = 15
SCHEDULE_SLOTS_PER_WEEK = 7 * 24 * 60 // SCHEDULE_SLOT_MINUTES
_SCHEDULE_VALUES = {0: MODE_ECO, 1: MODE_COMFORT}


def decode_schedule(programme: str) -> tuple[str, ...] | None:
    """Return one period name per 15-minute slot of the week, or None if invalid."""
    if len(programme) != SCHEDULE_SLOTS_PER_WEEK // 2:
        return None
    slots: list[str] = []
    for char in programme:
        try:
            value = int(char, 16)
        except ValueError:
            return None
        for bits in ((value >> 2) & 3, value & 3):
            slots.append(_SCHEDULE_VALUES.get(bits, f"{MODE_UNKNOWN}_{bits}"))
    return tuple(slots)


@dataclass(frozen=True, slots=True)
class ScheduleChange:
    """The next switch in the weekly schedule."""

    at: datetime
    period: str


def _slot_index(now: datetime) -> int:
    return now.weekday() * 96 + (now.hour * 60 + now.minute) // SCHEDULE_SLOT_MINUTES


def schedule_period_at(slots: tuple[str, ...], now: datetime) -> str:
    """Return the schedule period ("comfort"/"eco") active at `now` (local time)."""
    return slots[_slot_index(now)]


def next_schedule_change(slots: tuple[str, ...], now: datetime) -> ScheduleChange | None:
    """Return when the schedule next switches period, or None if it never does."""
    index = _slot_index(now)
    current = slots[index]
    slot_start = now.replace(minute=now.minute - now.minute % SCHEDULE_SLOT_MINUTES, second=0, microsecond=0)
    for step in range(1, SCHEDULE_SLOTS_PER_WEEK):
        period = slots[(index + step) % SCHEDULE_SLOTS_PER_WEEK]
        if period != current:
            # Wall-clock arithmetic: the schedule follows local time, also across DST.
            return ScheduleChange(at=slot_start + timedelta(minutes=SCHEDULE_SLOT_MINUTES * step), period=period)
    return None


# The device also reports the active period through its mode code.
SCHEDULE_PERIOD_BY_MODE: dict[str, str] = {
    MODE_PROGRAM_ON: MODE_COMFORT,
    "program_eco": MODE_ECO,
    "program_boost": MODE_BOOST,
}


def mode_from_code(mode_code: str) -> str:
    """Return a stable mode option string from an API code."""
    return MODE_CODE_TO_OPTION.get(mode_code, f"{MODE_UNKNOWN}_{mode_code}")


@dataclass(frozen=True, slots=True)
class WattsDeviceError:
    """A single device error object from smarthome/get_errors."""

    code: str
    title: str
    message: str


@dataclass(frozen=True, slots=True)
class WattsSmarthomeSummary:
    """Smarthome summary from user/read."""

    smarthome_id: str
    label: str
    mac_address: str


@dataclass(frozen=True, slots=True)
class WattsUserProfile:
    """User profile and smarthome list."""

    user_id: str
    email: str
    lang_code: str
    smarthomes: tuple[WattsSmarthomeSummary, ...]


@dataclass(frozen=True, slots=True)
class WattsZone:
    """Zone definition from smarthome/read."""

    num_zone: str
    zone_label: str
    zone_type_label: str
    device_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WattsDevice:
    """Device model normalized from smarthome/read and get_errors."""

    smarthome_id: str
    id_device: str
    name: str
    zone_id: str
    zone_name: str
    bundle_id: str
    gv_mode: str
    nv_mode: str
    temperature_air_raw: int | None
    temperature_floor_raw: int | None
    heating_up: bool
    error_code: int
    min_set_point_raw: int | None
    max_set_point_raw: int | None
    time_boost_seconds: int
    setpoints_raw: Mapping[str, int]
    errors: tuple[WattsDeviceError, ...] = ()
    schedule: tuple[str, ...] | None = None
    programme: str = ""

    @property
    def display_name(self) -> str:
        """Return a stable display name (zone name first: device names are often generic)."""
        return self.zone_name or self.name or self.id_device

    @property
    def current_mode(self) -> str:
        """Return mode option string from gv_mode code."""
        return mode_from_code(self.gv_mode)

    @property
    def is_off(self) -> bool:
        """Return True when the device is switched off."""
        return self.current_mode == MODE_OFF

    @property
    def is_program(self) -> bool:
        """Return True when the device follows its weekly schedule."""
        return self.current_mode in PROGRAM_MODES

    @property
    def is_boost(self) -> bool:
        """Return True when boost is active (manual or within the schedule)."""
        return self.current_mode in (MODE_BOOST, MODE_PROGRAM_BOOST)

    @property
    def heating_status(self) -> str:
        """Return normalized heating status."""
        return HEATING_ACTIVE if self.heating_up else HEATING_IDLE

    @property
    def current_air_temperature(self) -> float | None:
        """Return current air temperature in Celsius."""
        return raw_to_celsius(self.temperature_air_raw)

    @property
    def current_floor_temperature(self) -> float | None:
        """Return floor temperature in Celsius (None when no floor sensor)."""
        return raw_to_celsius(self.temperature_floor_raw)

    @property
    def min_set_point(self) -> float | None:
        """Return minimum setpoint in Celsius."""
        return raw_to_celsius(self.min_set_point_raw)

    @property
    def max_set_point(self) -> float | None:
        """Return maximum setpoint in Celsius."""
        return raw_to_celsius(self.max_set_point_raw)

    @property
    def active_setpoint_key(self) -> str | None:
        """Return the setpoint the current mode uses (None when off/unknown)."""
        return SETPOINT_BY_MODE.get(self.current_mode)

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature the device is currently aiming for."""
        key = self.active_setpoint_key
        return self.get_setpoint(key) if key else None

    def get_setpoint(self, key: str) -> float | None:
        """Return a setpoint in Celsius, on the 0.5 °C grid the thermostat uses."""
        celsius = raw_to_celsius(self.setpoints_raw.get(key))
        return None if celsius is None else round_to_step(celsius)

    def schedule_now(self, now: datetime) -> tuple[str | None, ScheduleChange | None]:
        """Return (active schedule period, next change) for local time `now`.

        Only meaningful while the device follows its schedule.
        """
        # The mode code is the device's live view; the schedule only predicts what comes next.
        period = SCHEDULE_PERIOD_BY_MODE.get(self.current_mode)
        if self.schedule is None:
            return period, None
        return period or schedule_period_at(self.schedule, now), next_schedule_change(self.schedule, now)

    def schedule_temperature(self, period: str | None) -> float | None:
        """Return the setpoint a schedule period uses."""
        key = SETPOINT_BY_MODE.get(period) if period else None
        return self.get_setpoint(key) if key else None

    def raw_field(self, name: str) -> str | None:
        """Return a raw API field as the string smarthome/read would send."""
        if name == FIELD_GV_MODE:
            return self.gv_mode
        if name == FIELD_NV_MODE:
            return self.nv_mode
        if name == FIELD_PROGRAMME:
            return self.programme
        if name == BOOST_TIMER:
            return str(self.time_boost_seconds)
        value = self.setpoints_raw.get(name)
        return None if value is None else str(value)

    def with_raw_fields(self, fields: Mapping[str, str]) -> WattsDevice:
        """Return a copy with raw API fields applied (used for optimistic state)."""
        changes: dict[str, Any] = {}
        setpoints = dict(self.setpoints_raw)
        for name, value in fields.items():
            if name == FIELD_GV_MODE:
                changes["gv_mode"] = value
            elif name == FIELD_NV_MODE:
                changes["nv_mode"] = value
            elif name == FIELD_PROGRAMME:
                changes["programme"] = value
                changes["schedule"] = decode_schedule(value)
            elif name in (*SETPOINT_KEYS, SETPOINT_MANUAL):
                parsed = _as_int(value)
                if parsed is not None:
                    setpoints[name] = parsed
        changes["setpoints_raw"] = setpoints
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class WattsSmarthome:
    """Smarthome model from smarthome/read with merged errors."""

    smarthome_id: str
    label: str
    mac_address: str
    unit_mode: str
    holiday_mode: str
    holiday_start: str
    holiday_end: str
    zones: tuple[WattsZone, ...]
    devices: tuple[WattsDevice, ...]
    seconds_since_contact: int | None = None
    devices_by_id: dict[str, WattsDevice] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "devices_by_id", {device.id_device: device for device in self.devices})

    def get_device(self, id_device: str) -> WattsDevice | None:
        """Return a device by short device id."""
        return self.devices_by_id.get(id_device)

    def holiday_active(self, now: datetime) -> bool:
        """Return True when holiday mode is running (the app blocks edits then).

        `now` must be a naive datetime in the central unit's local time.
        """
        if self.holiday_start in _UNSET_HOLIDAY_DATES or self.holiday_end in _UNSET_HOLIDAY_DATES:
            return False
        try:
            start = datetime.strptime(self.holiday_start, _HOLIDAY_DATE_FORMAT)
            end = datetime.strptime(self.holiday_end, _HOLIDAY_DATE_FORMAT)
        except ValueError:
            return False
        return start <= now <= end

    def with_devices(self, devices: tuple[WattsDevice, ...]) -> WattsSmarthome:
        """Return copy with a new device tuple."""
        return replace(self, devices=devices)


@dataclass(frozen=True, slots=True)
class WattsState:
    """Coordinator snapshot for all user and smarthome data."""

    user: WattsUserProfile
    smarthomes: tuple[WattsSmarthome, ...]
    smarthomes_by_id: dict[str, WattsSmarthome] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "smarthomes_by_id", {home.smarthome_id: home for home in self.smarthomes})

    def get_smarthome(self, smarthome_id: str) -> WattsSmarthome | None:
        """Return smarthome by id."""
        return self.smarthomes_by_id.get(smarthome_id)

    def get_device(self, smarthome_id: str, id_device: str) -> WattsDevice | None:
        """Return device by smarthome and short device id."""
        home = self.get_smarthome(smarthome_id)
        return home.get_device(id_device) if home else None


@dataclass(frozen=True, slots=True)
class WattsWriteRequest:
    """One device command for query/push."""

    smarthome_id: str
    id_device: str
    query: dict[str, str]


# --- Parsers -----------------------------------------------------------------------


def parse_user_profile(payload: Mapping[str, Any]) -> WattsUserProfile:
    """Parse user/read response into domain model."""
    data = payload.get("data") or {}

    smarthomes: list[WattsSmarthomeSummary] = []
    for raw in data.get("smarthomes") or []:
        smarthome_id = _as_str(raw.get("smarthome_id"))
        if not smarthome_id:
            continue
        smarthomes.append(
            WattsSmarthomeSummary(
                smarthome_id=smarthome_id,
                label=_as_str(raw.get("label")),
                mac_address=_as_str(raw.get("mac_address")),
            )
        )

    return WattsUserProfile(
        user_id=_as_str(data.get("user_id")),
        email=_as_str(data.get("email")),
        lang_code=_as_str(data.get("lang_code")),
        smarthomes=tuple(smarthomes),
    )


def _parse_device(raw_device: Mapping[str, Any], smarthome_id: str, zone: WattsZone | None) -> WattsDevice:
    setpoints_raw: dict[str, int] = {}
    for setpoint_key in (*SETPOINT_KEYS, SETPOINT_MANUAL):
        raw_value = _as_int(raw_device.get(setpoint_key))
        if raw_value is not None:
            setpoints_raw[setpoint_key] = raw_value

    return WattsDevice(
        smarthome_id=smarthome_id,
        id_device=_as_str(raw_device.get(FIELD_ID_DEVICE)),
        name=_as_str(raw_device.get("nom_appareil")),
        zone_id=zone.num_zone if zone else _as_str(raw_device.get("num_zone")),
        zone_name=zone.zone_label if zone else "",
        bundle_id=_as_str(raw_device.get("bundle_id")),
        gv_mode=_as_str(raw_device.get(FIELD_GV_MODE)),
        nv_mode=_as_str(raw_device.get(FIELD_NV_MODE)),
        temperature_air_raw=_as_int(raw_device.get("temperature_air")),
        temperature_floor_raw=_as_int(raw_device.get("temperature_sol")),
        heating_up=_as_str(raw_device.get("heating_up")) == "1",
        error_code=_as_int(raw_device.get("error_code")) or 0,
        min_set_point_raw=_as_int(raw_device.get("min_set_point")),
        max_set_point_raw=_as_int(raw_device.get("max_set_point")),
        time_boost_seconds=_as_int(raw_device.get(BOOST_TIMER)) or 0,
        setpoints_raw=setpoints_raw,
        schedule=decode_schedule(_as_str(raw_device.get(FIELD_PROGRAMME))),
        programme=_as_str(raw_device.get(FIELD_PROGRAMME)),
    )


def parse_smarthome(payload: Mapping[str, Any], *, smarthome_id: str = "") -> WattsSmarthome:
    """Parse smarthome/read response into domain model."""
    data = payload.get("data") or {}
    resolved_smarthome_id = _as_str(data.get("smarthome_id")) or smarthome_id

    zones: list[WattsZone] = []
    zone_lookup: dict[str, WattsZone] = {}
    for zone_raw in data.get("zones") or []:
        device_ids = tuple(
            device_id
            for zone_device in zone_raw.get("devices") or []
            if isinstance(zone_device, dict) and (device_id := _as_str(zone_device.get(FIELD_ID_DEVICE)))
        )
        zone = WattsZone(
            num_zone=_as_str(zone_raw.get("num_zone")),
            zone_label=_as_str(zone_raw.get("zone_label")),
            zone_type_label=_as_str(zone_raw.get("label_zone_type")),
            device_ids=device_ids,
        )
        zones.append(zone)
        for device_id in device_ids:
            zone_lookup[device_id] = zone

    devices_by_id: dict[str, WattsDevice] = {}
    raw_devices = [d for d in data.get("devices") or [] if isinstance(d, dict)]
    for zone_raw in data.get("zones") or []:
        raw_devices.extend(d for d in zone_raw.get("devices") or [] if isinstance(d, dict))

    for raw_device in raw_devices:
        id_device = _as_str(raw_device.get(FIELD_ID_DEVICE))
        if id_device and id_device not in devices_by_id:
            devices_by_id[id_device] = _parse_device(raw_device, resolved_smarthome_id, zone_lookup.get(id_device))

    return WattsSmarthome(
        smarthome_id=resolved_smarthome_id,
        label=_as_str(data.get("label")),
        mac_address=_as_str(data.get("mac_address")),
        unit_mode=_as_str(data.get("param_c_f")),
        holiday_mode=_as_str(data.get("holiday_mode")),
        holiday_start=_as_str(data.get("holiday_start")),
        holiday_end=_as_str(data.get("holiday_end")),
        zones=tuple(zones),
        devices=tuple(devices_by_id.values()),
    )


def parse_smarthome_errors(payload: Mapping[str, Any]) -> dict[str, tuple[WattsDeviceError, ...]]:
    """Parse smarthome/get_errors response into per-device error map."""
    results = (payload.get("data") or {}).get("results") or {}
    by_device = results.get("by_device") or {}

    parsed: dict[str, tuple[WattsDeviceError, ...]] = {}
    for smarthome_data in by_device.values():
        if not isinstance(smarthome_data, dict):
            continue
        for raw_device in smarthome_data.values():
            if not isinstance(raw_device, dict):
                continue
            id_device = _as_str(raw_device.get(FIELD_ID_DEVICE))
            if not id_device:
                continue
            parsed[id_device] = tuple(
                WattsDeviceError(
                    code=_as_str(raw_error.get("code")),
                    title=_as_str(raw_error.get("title")),
                    message=_as_str(raw_error.get("error")),
                )
                for raw_error in raw_device.get("errors") or []
                if isinstance(raw_error, dict)
            )
    return parsed


def parse_state(
    *,
    user_payload: Mapping[str, Any],
    smarthome_payloads: Mapping[str, Mapping[str, Any]],
    smarthome_error_payloads: Mapping[str, Mapping[str, Any]],
    connection_seconds: Mapping[str, int | None] | None = None,
) -> WattsState:
    """Build a WattsState from user + smarthome payloads."""
    user = parse_user_profile(user_payload)

    homes: list[WattsSmarthome] = []
    for summary in user.smarthomes:
        smarthome_payload = smarthome_payloads.get(summary.smarthome_id)
        if smarthome_payload is None:
            continue

        home = parse_smarthome(smarthome_payload, smarthome_id=summary.smarthome_id)
        error_payload = smarthome_error_payloads.get(summary.smarthome_id)
        if error_payload:
            error_map = parse_smarthome_errors(error_payload)
            home = home.with_devices(
                tuple(replace(device, errors=error_map.get(device.id_device, ())) for device in home.devices)
            )
        if connection_seconds is not None:
            home = replace(home, seconds_since_contact=connection_seconds.get(summary.smarthome_id))
        homes.append(home)

    return WattsState(user=user, smarthomes=tuple(homes))


# --- Command builders ----------------------------------------------------------------
# These mirror the web app's `saveChoice` / `goBoostTimer` queries: only the
# fields that change are sent, never a full copy of the device state.


def clamp_boost_seconds(seconds: int) -> int:
    """Clamp a boost duration to what the app accepts."""
    return max(MIN_BOOST_SECONDS, min(MAX_BOOST_SECONDS, int(seconds)))


def build_mode_write_request(
    *,
    device: WattsDevice,
    selected_mode: str,
    boost_seconds: int | None = None,
) -> WattsWriteRequest:
    """Build a query/push payload that switches the device to another mode."""
    if selected_mode not in SELECTABLE_MODES:
        raise ValueError(f"Unsupported mode option: {selected_mode}")
    mode_code = MODE_OPTION_TO_CODE[selected_mode]

    query: dict[str, str] = {FIELD_ID_DEVICE: device.id_device}
    if selected_mode == MODE_BOOST:
        seconds = boost_seconds or device.time_boost_seconds or DEFAULT_BOOST_SECONDS
        query[BOOST_TIMER] = str(clamp_boost_seconds(seconds))
    else:
        query[BOOST_TIMER] = "0"

    if selected_mode == MODE_OFF:
        query[SETPOINT_MANUAL] = "0"
    elif selected_mode == MODE_PROGRAM_ON:
        comfort = device.setpoints_raw.get(SETPOINT_COMFORT)
        if comfort is not None:
            query[SETPOINT_MANUAL] = str(comfort)
    else:
        setpoint_key = SETPOINT_BY_MODE[selected_mode]
        raw_value = device.setpoints_raw.get(setpoint_key)
        if raw_value is not None:
            query[setpoint_key] = str(raw_value)
            query[SETPOINT_MANUAL] = str(raw_value)

    query[FIELD_GV_MODE] = mode_code
    query[FIELD_NV_MODE] = mode_code
    return WattsWriteRequest(smarthome_id=device.smarthome_id, id_device=device.id_device, query=query)


def build_setpoint_write_request(
    *,
    device: WattsDevice,
    setpoint_key: str,
    value_celsius: float,
) -> WattsWriteRequest:
    """Build a query/push payload that changes one setpoint and keeps the mode."""
    if setpoint_key not in (*SETPOINT_KEYS, SETPOINT_MANUAL):
        raise ValueError(f"Unsupported setpoint key: {setpoint_key}")

    raw_value = str(celsius_to_raw(round_to_step(value_celsius)))
    query: dict[str, str] = {FIELD_ID_DEVICE: device.id_device, setpoint_key: raw_value}
    if device.active_setpoint_key == setpoint_key:
        query[SETPOINT_MANUAL] = raw_value
    query[FIELD_GV_MODE] = device.gv_mode
    query[FIELD_NV_MODE] = device.nv_mode or device.gv_mode
    return WattsWriteRequest(smarthome_id=device.smarthome_id, id_device=device.id_device, query=query)


def build_boost_write_request(*, device: WattsDevice, boost_seconds: int) -> WattsWriteRequest:
    """Build a query/push payload that (re)starts boost for a duration."""
    return build_mode_write_request(device=device, selected_mode=MODE_BOOST, boost_seconds=boost_seconds)


def merge_queries(base: Mapping[str, str], update: Mapping[str, str]) -> dict[str, str]:
    """Merge two queued queries for the same device; later fields win."""
    merged = dict(base)
    merged.update(update)
    return merged
