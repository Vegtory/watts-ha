"""Domain models and mappers for Watts SmartHome."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .const import (
    BOOST_TIMER,
    HEATING_ACTIVE,
    HEATING_IDLE,
    MODE_BOOST,
    MODE_CODE_TO_OPTION,
    MODE_OPTION_TO_CODE,
    MODE_UNKNOWN,
    RAW_TEMPERATURE_FACTOR,
    SETPOINT_ANTI_FROST,
    SETPOINT_BOOST,
    SETPOINT_BY_MODE,
    SETPOINT_COMFORT,
    SETPOINT_ECO,
    SETPOINT_KEYS,
    SETPOINT_MANUAL,
)


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
    """Convert Watts raw temperature to Celsius."""
    if raw_value is None:
        return None
    raw_int = _as_int(raw_value)
    if raw_int is None:
        return None
    return round(raw_int / RAW_TEMPERATURE_FACTOR, 1)


def celsius_to_raw(temperature: float) -> int:
    """Convert Celsius value to Watts raw temperature."""
    return int(round(temperature * RAW_TEMPERATURE_FACTOR))


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
    address: str
    latitude: str
    longitude: str
    mac_address: str
    general_mode: str
    holiday_mode: str
    unit_mode: str


@dataclass(frozen=True, slots=True)
class WattsUserProfile:
    """User profile and smarthome list."""

    user_id: str
    email: str
    lang_code: str
    cgu_id: str
    optin_stats: str
    smarthomes: tuple[WattsSmarthomeSummary, ...]


@dataclass(frozen=True, slots=True)
class WattsUserRef:
    """A user entry attached to a smarthome."""

    user_id: str
    user_email: str


@dataclass(frozen=True, slots=True)
class WattsModeInfo:
    """Mode metadata entry from smarthome/read."""

    smarthome_id: str
    mode_type_id: str
    bundle_id: str
    nvgv_mode_id: str


@dataclass(frozen=True, slots=True)
class WattsZone:
    """Zone definition from smarthome/read."""

    num_zone: str
    zone_label: str
    zone_type_label: str
    zone_type_icon: str
    zone_image_id: str
    device_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WattsDevice:
    """Device model normalized from smarthome/read and get_errors."""

    smarthome_id: str
    id: str
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
    setpoints_raw: dict[str, int]
    errors: tuple[WattsDeviceError, ...]

    @property
    def display_name(self) -> str:
        """Return a stable display name."""
        if self.name:
            return self.name
        if self.zone_name:
            return self.zone_name
        return self.id_device

    @property
    def current_mode(self) -> str:
        """Return mode option string from gv_mode code."""
        mapped = MODE_CODE_TO_OPTION.get(self.gv_mode)
        if mapped is not None:
            return mapped
        return f"{MODE_UNKNOWN}_{self.gv_mode}"

    @property
    def heating_status(self) -> str:
        """Return normalized heating status."""
        return HEATING_ACTIVE if self.heating_up else HEATING_IDLE

    @property
    def current_air_temperature(self) -> float | None:
        """Return current air temperature in Celsius."""
        return raw_to_celsius(self.temperature_air_raw)

    @property
    def min_set_point(self) -> float | None:
        """Return minimum setpoint in Celsius."""
        return raw_to_celsius(self.min_set_point_raw)

    @property
    def max_set_point(self) -> float | None:
        """Return maximum setpoint in Celsius."""
        return raw_to_celsius(self.max_set_point_raw)

    def get_setpoint(self, key: str) -> float | None:
        """Return a setpoint in Celsius by raw key."""
        raw = self.setpoints_raw.get(key)
        return raw_to_celsius(raw)

    def get_setpoint_raw(self, key: str) -> str | None:
        """Return raw setpoint value as string."""
        raw = self.setpoints_raw.get(key)
        if raw is None:
            return None
        return str(raw)

    def base_query(self) -> dict[str, str]:
        """Build a full query payload from current device state."""
        query: dict[str, str] = {
            "id_device": self.id_device,
            "gv_mode": self.gv_mode,
            "nv_mode": self.nv_mode,
            BOOST_TIMER: str(self.time_boost_seconds),
        }

        for setpoint_key in (*SETPOINT_KEYS, SETPOINT_MANUAL):
            raw_value = self.get_setpoint_raw(setpoint_key)
            if raw_value is not None:
                query[setpoint_key] = raw_value

        if SETPOINT_MANUAL not in query:
            fallback_key = SETPOINT_BY_MODE.get(self.current_mode)
            if fallback_key is not None:
                fallback_value = self.get_setpoint_raw(fallback_key)
                if fallback_value is not None:
                    query[SETPOINT_MANUAL] = fallback_value

        return query

    def with_errors(self, errors: tuple[WattsDeviceError, ...]) -> WattsDevice:
        """Return a copy with updated errors."""
        return replace(self, errors=errors)


@dataclass(frozen=True, slots=True)
class WattsSmarthome:
    """Smarthome model from smarthome/read with merged errors."""

    smarthome_id: str
    label: str
    address: str
    latitude: str
    longitude: str
    mac_address: str
    general_mode: str
    holiday_mode: str
    unit_mode: str
    holiday_start: str
    holiday_end: str
    jet_lag: int
    users: tuple[WattsUserRef, ...]
    modes: tuple[WattsModeInfo, ...]
    zones: tuple[WattsZone, ...]
    devices: tuple[WattsDevice, ...]

    @property
    def devices_by_id(self) -> dict[str, WattsDevice]:
        """Return devices keyed by short id."""
        return {device.id_device: device for device in self.devices}

    def get_device(self, id_device: str) -> WattsDevice:
        """Return a device by short device id."""
        return self.devices_by_id[id_device]

    def with_error_map(self, error_map: dict[str, tuple[WattsDeviceError, ...]]) -> WattsSmarthome:
        """Return copy with per-device errors merged in."""
        updated_devices = tuple(device.with_errors(error_map.get(device.id_device, ())) for device in self.devices)
        return replace(self, devices=updated_devices)


@dataclass(frozen=True, slots=True)
class WattsState:
    """Coordinator snapshot for all user and smarthome data."""

    user: WattsUserProfile
    smarthomes: tuple[WattsSmarthome, ...]

    @property
    def smarthomes_by_id(self) -> dict[str, WattsSmarthome]:
        """Return smarthomes keyed by smarthome id."""
        return {home.smarthome_id: home for home in self.smarthomes}

    def get_smarthome(self, smarthome_id: str) -> WattsSmarthome:
        """Return smarthome by id."""
        return self.smarthomes_by_id[smarthome_id]

    def get_device(self, smarthome_id: str, id_device: str) -> WattsDevice:
        """Return device by smarthome and short device id."""
        return self.get_smarthome(smarthome_id).get_device(id_device)


@dataclass(frozen=True, slots=True)
class WattsWriteRequest:
    """Write request describing one device update."""

    smarthome_id: str
    id_device: str
    query: dict[str, str]


def parse_user_profile(payload: dict[str, Any]) -> WattsUserProfile:
    """Parse user/read response into domain model."""
    data = payload.get("data") or {}

    smarthomes: list[WattsSmarthomeSummary] = []
    for raw in data.get("smarthomes", []):
        smarthome_id = _as_str(raw.get("smarthome_id"))
        if not smarthome_id:
            continue
        smarthomes.append(
            WattsSmarthomeSummary(
                smarthome_id=smarthome_id,
                label=_as_str(raw.get("label")),
                address=_as_str(raw.get("address_position")),
                latitude=_as_str(raw.get("latitude")),
                longitude=_as_str(raw.get("longitude")),
                mac_address=_as_str(raw.get("mac_address")),
                general_mode=_as_str(raw.get("general_mode")),
                holiday_mode=_as_str(raw.get("holiday_mode")),
                unit_mode=_as_str(raw.get("param_c_f")),
            )
        )

    return WattsUserProfile(
        user_id=_as_str(data.get("user_id")),
        email=_as_str(data.get("email")),
        lang_code=_as_str(data.get("lang_code")),
        cgu_id=_as_str(data.get("cgu_id")),
        optin_stats=_as_str(data.get("optin_stats")),
        smarthomes=tuple(smarthomes),
    )


def parse_smarthome(payload: dict[str, Any], *, smarthome_id: str = "") -> WattsSmarthome:
    """Parse smarthome/read response into domain model."""
    data = payload.get("data") or {}
    resolved_smarthome_id = _as_str(data.get("smarthome_id")) or smarthome_id

    zones: list[WattsZone] = []
    zone_lookup: dict[str, WattsZone] = {}
    for zone_raw in data.get("zones", []):
        device_ids: list[str] = []
        for zone_device in zone_raw.get("devices", []):
            zone_device_id = _as_str(zone_device.get("id_device"))
            if zone_device_id:
                device_ids.append(zone_device_id)

        zone = WattsZone(
            num_zone=_as_str(zone_raw.get("num_zone")),
            zone_label=_as_str(zone_raw.get("zone_label")),
            zone_type_label=_as_str(zone_raw.get("label_zone_type")),
            zone_type_icon=_as_str(zone_raw.get("picto_zone_type")),
            zone_image_id=_as_str(zone_raw.get("zone_img_id")),
            device_ids=tuple(device_ids),
        )
        zones.append(zone)
        for zone_device_id in device_ids:
            zone_lookup[zone_device_id] = zone

    devices_by_id: dict[str, WattsDevice] = {}

    def add_raw_device(raw_device: dict[str, Any]) -> None:
        id_device = _as_str(raw_device.get("id_device"))
        if not id_device or id_device in devices_by_id:
            return

        zone = zone_lookup.get(id_device)
        zone_name = zone.zone_label if zone else ""

        setpoints_raw: dict[str, int] = {}
        for setpoint_key in (*SETPOINT_KEYS, SETPOINT_MANUAL):
            raw_value = _as_int(raw_device.get(setpoint_key))
            if raw_value is not None:
                setpoints_raw[setpoint_key] = raw_value

        devices_by_id[id_device] = WattsDevice(
            smarthome_id=resolved_smarthome_id,
            id=_as_str(raw_device.get("id")),
            id_device=id_device,
            name=_as_str(raw_device.get("nom_appareil")),
            zone_id=zone.num_zone if zone else _as_str(raw_device.get("num_zone")),
            zone_name=zone_name,
            bundle_id=_as_str(raw_device.get("bundle_id")),
            gv_mode=_as_str(raw_device.get("gv_mode")),
            nv_mode=_as_str(raw_device.get("nv_mode")),
            temperature_air_raw=_as_int(raw_device.get("temperature_air")),
            temperature_floor_raw=_as_int(raw_device.get("temperature_sol")),
            heating_up=_as_str(raw_device.get("heating_up")) == "1",
            error_code=_as_int(raw_device.get("error_code")) or 0,
            min_set_point_raw=_as_int(raw_device.get("min_set_point")),
            max_set_point_raw=_as_int(raw_device.get("max_set_point")),
            time_boost_seconds=_as_int(raw_device.get(BOOST_TIMER)) or 0,
            setpoints_raw=setpoints_raw,
            errors=(),
        )

    for raw_device in data.get("devices", []):
        if isinstance(raw_device, dict):
            add_raw_device(raw_device)

    for zone_raw in data.get("zones", []):
        for zone_device in zone_raw.get("devices", []):
            if isinstance(zone_device, dict):
                add_raw_device(zone_device)

    users = tuple(
        WattsUserRef(
            user_id=_as_str(raw_user.get("user_id")),
            user_email=_as_str(raw_user.get("user_email")),
        )
        for raw_user in data.get("users", [])
    )

    modes = tuple(
        WattsModeInfo(
            smarthome_id=_as_str(raw_mode.get("smarthome_id")),
            mode_type_id=_as_str(raw_mode.get("smarthome_mode_type_id")),
            bundle_id=_as_str(raw_mode.get("bundle_id")),
            nvgv_mode_id=_as_str(raw_mode.get("nvgv_mode_id")),
        )
        for raw_mode in data.get("modes", [])
    )

    return WattsSmarthome(
        smarthome_id=resolved_smarthome_id,
        label=_as_str(data.get("label")),
        address=_as_str(data.get("address_position")),
        latitude=_as_str(data.get("latitude")),
        longitude=_as_str(data.get("longitude")),
        mac_address=_as_str(data.get("mac_address")),
        general_mode=_as_str(data.get("general_mode")),
        holiday_mode=_as_str(data.get("holiday_mode")),
        unit_mode=_as_str(data.get("param_c_f")),
        holiday_start=_as_str(data.get("holiday_start")),
        holiday_end=_as_str(data.get("holiday_end")),
        jet_lag=_as_int(data.get("jet_lag")) or 0,
        users=users,
        modes=modes,
        zones=tuple(zones),
        devices=tuple(devices_by_id.values()),
    )


def parse_smarthome_errors(payload: dict[str, Any]) -> dict[str, tuple[WattsDeviceError, ...]]:
    """Parse smarthome/get_errors response into per-device error map."""
    results = ((payload.get("data") or {}).get("results") or {})
    by_device = results.get("by_device") or {}

    parsed: dict[str, tuple[WattsDeviceError, ...]] = {}

    for smarthome_data in by_device.values():
        if not isinstance(smarthome_data, dict):
            continue
        for raw_device in smarthome_data.values():
            if not isinstance(raw_device, dict):
                continue

            id_device = _as_str(raw_device.get("id_device"))
            if not id_device:
                continue

            errors = tuple(
                WattsDeviceError(
                    code=_as_str(raw_error.get("code")),
                    title=_as_str(raw_error.get("title")),
                    message=_as_str(raw_error.get("error")),
                )
                for raw_error in raw_device.get("errors", [])
                if isinstance(raw_error, dict)
            )
            parsed[id_device] = errors

    return parsed


def parse_state(
    *,
    user_payload: dict[str, Any],
    smarthome_payloads: dict[str, dict[str, Any]],
    smarthome_error_payloads: dict[str, dict[str, Any]],
) -> WattsState:
    """Build a WattsState from user + smarthome payloads."""
    user = parse_user_profile(user_payload)

    homes: list[WattsSmarthome] = []
    for summary in user.smarthomes:
        smarthome_payload = smarthome_payloads.get(summary.smarthome_id)
        if smarthome_payload is None:
            continue

        smarthome = parse_smarthome(smarthome_payload, smarthome_id=summary.smarthome_id)
        error_payload = smarthome_error_payloads.get(summary.smarthome_id)
        if error_payload is not None:
            smarthome = smarthome.with_error_map(parse_smarthome_errors(error_payload))
        homes.append(smarthome)

    return WattsState(user=user, smarthomes=tuple(homes))


def build_mode_write_request(
    *,
    device: WattsDevice,
    selected_mode: str,
) -> WattsWriteRequest:
    """Build a query/push payload for mode updates."""
    mode_code = MODE_OPTION_TO_CODE.get(selected_mode)
    if mode_code is None:
        raise ValueError(f"Unsupported mode option: {selected_mode}")

    query = device.base_query()
    query["gv_mode"] = mode_code
    query["nv_mode"] = mode_code

    setpoint_key = SETPOINT_BY_MODE.get(selected_mode)
    if setpoint_key is not None:
        mode_setpoint_raw = device.get_setpoint_raw(setpoint_key)
        if mode_setpoint_raw is not None:
            query[setpoint_key] = mode_setpoint_raw
            query[SETPOINT_MANUAL] = mode_setpoint_raw

    if selected_mode == MODE_BOOST and BOOST_TIMER not in query:
        query[BOOST_TIMER] = "3600"

    return WattsWriteRequest(smarthome_id=device.smarthome_id, id_device=device.id_device, query=query)


def build_setpoint_write_request(
    *,
    device: WattsDevice,
    setpoint_key: str,
    value_celsius: float,
) -> WattsWriteRequest:
    """Build a query/push payload for one setpoint update."""
    if setpoint_key not in (*SETPOINT_KEYS,):
        raise ValueError(f"Unsupported setpoint key: {setpoint_key}")

    query = device.base_query()
    raw_value = str(celsius_to_raw(value_celsius))
    query[setpoint_key] = raw_value

    active_setpoint_key = SETPOINT_BY_MODE.get(device.current_mode)
    if active_setpoint_key == setpoint_key:
        query[SETPOINT_MANUAL] = raw_value

    return WattsWriteRequest(smarthome_id=device.smarthome_id, id_device=device.id_device, query=query)


def build_boost_timer_write_request(
    *,
    device: WattsDevice,
    value_seconds: int,
) -> WattsWriteRequest:
    """Build a query/push payload for boost timer update."""
    query = device.base_query()
    query[BOOST_TIMER] = str(max(0, value_seconds))

    return WattsWriteRequest(smarthome_id=device.smarthome_id, id_device=device.id_device, query=query)


def current_mode_label(device: WattsDevice) -> str:
    """Compatibility helper used by sensor/select entities."""
    return device.current_mode


def get_current_mode_code(mode_option: str) -> str | None:
    """Return API mode code for a mode option."""
    return MODE_OPTION_TO_CODE.get(mode_option)


def mode_from_code(mode_code: str) -> str:
    """Return a stable mode option string from an API code."""
    mapped = MODE_CODE_TO_OPTION.get(mode_code)
    if mapped is not None:
        return mapped
    return f"{MODE_UNKNOWN}_{mode_code}"


def default_manual_setpoint_key(mode_option: str) -> str:
    """Return the setpoint key associated with a mode."""
    return SETPOINT_BY_MODE.get(mode_option, SETPOINT_COMFORT)


def all_setpoint_keys() -> tuple[str, ...]:
    """Return all available setpoint keys."""
    return SETPOINT_KEYS


def setpoint_name(setpoint_key: str) -> str:
    """Return a human name for a setpoint key."""
    if setpoint_key == SETPOINT_COMFORT:
        return "comfort"
    if setpoint_key == SETPOINT_ECO:
        return "eco"
    if setpoint_key == SETPOINT_ANTI_FROST:
        return "anti_frost"
    if setpoint_key == SETPOINT_BOOST:
        return "boost"
    return setpoint_key
