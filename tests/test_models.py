"""Tests for Watts domain model parsing and write payload builders."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.watts_smarthome.const import (
    MODE_ANTI_FROST,
    MODE_BOOST,
    MODE_COMFORT,
    MODE_ECO,
    MODE_OFF,
    MODE_PROGRAM_ON,
    SETPOINT_BOOST,
    SETPOINT_COMFORT,
    SETPOINT_ECO,
)
from custom_components.watts_smarthome.models import (
    ScheduleChange,
    build_mode_write_request,
    build_setpoint_write_request,
    celsius_to_raw,
    decode_schedule,
    next_schedule_change,
    parse_smarthome,
    parse_state,
    raw_to_celsius,
)

from .conftest import SMARTHOME_ID, load_fixture


@pytest.fixture
def state():
    return parse_state(
        user_payload=load_fixture("user_read"),
        smarthome_payloads={SMARTHOME_ID: load_fixture("smarthome_read")},
        smarthome_error_payloads={SMARTHOME_ID: load_fixture("get_errors")},
        connection_seconds={SMARTHOME_ID: 7},
    )


def test_temperature_conversion() -> None:
    assert raw_to_celsius(446) == 7.0
    assert raw_to_celsius("680") == 20.0
    assert celsius_to_raw(19.5) == 671
    assert celsius_to_raw(18.0) == 644
    # 2124 (212.4 F) is the "no sensor" marker.
    assert raw_to_celsius(2124) is None
    assert raw_to_celsius(None) is None
    assert raw_to_celsius("") is None


def test_parse_state(state) -> None:
    home = state.get_smarthome(SMARTHOME_ID)
    assert home.seconds_since_contact == 7
    assert home.mac_address == "00:11:22:33:44:55"

    device = state.get_device(SMARTHOME_ID, "C001-000")
    assert device.display_name == "Living room"
    assert device.current_air_temperature == 21.4
    assert device.current_floor_temperature is None
    assert device.current_mode == MODE_PROGRAM_ON
    assert device.is_program
    # 672 raw = 19.56 °C, shown on the thermostat's 0.5 °C grid.
    assert device.target_temperature == 19.5
    assert device.min_set_point == 5.0
    assert device.max_set_point == 37.0
    assert [e.code for e in device.errors] == ["DEF_BAT_TH"]

    eco = state.get_device(SMARTHOME_ID, "C002-001")
    assert eco.current_mode == MODE_ECO
    assert eco.target_temperature == 18.0
    assert eco.errors == ()

    assert state.get_device(SMARTHOME_ID, "missing") is None


@pytest.mark.parametrize(
    ("code", "mode"),
    [("11", "program_eco"), ("13", "program"), ("15", "manual"), ("16", "program_boost"), ("99", "unknown_99")],
)
def test_mode_codes(code: str, mode: str) -> None:
    payload = load_fixture("smarthome_read")
    payload["data"]["zones"][0]["devices"][0]["gv_mode"] = code
    payload["data"]["devices"][0]["gv_mode"] = code
    device = parse_smarthome(payload).get_device("C001-000")
    assert device.current_mode == mode


def test_holiday_detection() -> None:
    payload = load_fixture("smarthome_read")
    home = parse_smarthome(payload)
    assert not home.holiday_active(datetime(2026, 1, 1))

    payload["data"]["holiday_start"] = "2026-07-01 00:00:00"
    payload["data"]["holiday_end"] = "2026-07-14 00:00:00"
    home = parse_smarthome(payload)
    assert home.holiday_active(datetime(2026, 7, 5, 12))
    assert not home.holiday_active(datetime(2026, 7, 15))


# The expected queries below are copied from a browser capture of the official app.


def test_mode_queries_match_app(state) -> None:
    device = state.get_device(SMARTHOME_ID, "C001-000")

    assert build_mode_write_request(device=device, selected_mode=MODE_COMFORT).query == {
        "id_device": "C001-000",
        "time_boost": "0",
        "consigne_confort": "672",
        "consigne_manuel": "672",
        "gv_mode": "0",
        "nv_mode": "0",
    }
    assert build_mode_write_request(device=device, selected_mode=MODE_ECO).query == {
        "id_device": "C001-000",
        "time_boost": "0",
        "consigne_eco": "644",
        "consigne_manuel": "644",
        "gv_mode": "3",
        "nv_mode": "3",
    }
    assert build_mode_write_request(device=device, selected_mode=MODE_ANTI_FROST).query["consigne_hg"] == "446"
    assert build_mode_write_request(device=device, selected_mode=MODE_BOOST, boost_seconds=7140).query == {
        "id_device": "C001-000",
        "time_boost": "7140",
        "consigne_boost": "681",
        "consigne_manuel": "681",
        "gv_mode": "4",
        "nv_mode": "4",
    }
    assert build_mode_write_request(device=device, selected_mode=MODE_PROGRAM_ON).query == {
        "id_device": "C001-000",
        "time_boost": "0",
        "consigne_manuel": "672",
        "gv_mode": "8",
        "nv_mode": "8",
    }
    off = build_mode_write_request(device=device, selected_mode=MODE_OFF).query
    assert off["gv_mode"] == "1"
    assert off["consigne_manuel"] == "0"

    with pytest.raises(ValueError):
        build_mode_write_request(device=device, selected_mode="program_eco")


def test_boost_duration_is_clamped(state) -> None:
    device = state.get_device(SMARTHOME_ID, "C001-000")
    query = build_mode_write_request(device=device, selected_mode=MODE_BOOST, boost_seconds=10).query
    assert query["time_boost"] == "180"


def test_setpoint_queries(state) -> None:
    eco_device = state.get_device(SMARTHOME_ID, "C002-001")

    # Active setpoint: also update consigne_manuel, keep the mode.
    assert build_setpoint_write_request(device=eco_device, setpoint_key=SETPOINT_ECO, value_celsius=18.5).query == {
        "id_device": "C002-001",
        "consigne_eco": str(celsius_to_raw(18.5)),
        "consigne_manuel": str(celsius_to_raw(18.5)),
        "gv_mode": "3",
        "nv_mode": "3",
    }
    # Inactive setpoint: only that value changes.
    query = build_setpoint_write_request(device=eco_device, setpoint_key=SETPOINT_COMFORT, value_celsius=21).query
    assert "consigne_manuel" not in query
    assert query["consigne_confort"] == str(celsius_to_raw(21))

    with pytest.raises(ValueError):
        build_setpoint_write_request(device=eco_device, setpoint_key="bogus", value_celsius=20)

    assert (
        SETPOINT_BOOST
        in build_setpoint_write_request(device=eco_device, setpoint_key=SETPOINT_BOOST, value_celsius=22).query
    )


def test_optimistic_overlay(state) -> None:
    device = state.get_device(SMARTHOME_ID, "C002-001")
    updated = device.with_raw_fields({"gv_mode": "0", "nv_mode": "0", "consigne_confort": "680"})
    assert updated.current_mode == MODE_COMFORT
    assert updated.target_temperature == 20.0
    assert updated.raw_field("gv_mode") == "0"
    # Original is unchanged.
    assert device.current_mode == MODE_ECO


def test_setpoint_writes_snap_to_half_degrees(state) -> None:
    device = state.get_device(SMARTHOME_ID, "C002-001")
    query = build_setpoint_write_request(device=device, setpoint_key=SETPOINT_ECO, value_celsius=20.3).query
    assert query["consigne_eco"] == str(celsius_to_raw(20.5)) == "689"
    query = build_setpoint_write_request(device=device, setpoint_key=SETPOINT_ECO, value_celsius=20.2).query
    assert query["consigne_eco"] == str(celsius_to_raw(20.0))


# Real programme string from a browser capture, with the blocks the app's
# sandbox/convert_program returned for it.
CAPTURED_PROGRAMME = (
    "000000000000000000000000000000005555555555500000"
    "000000000000000000000000000000005555555555500000"
    "000000000000000000000000000000005555555555500000"
    "000000000000000000000000000000005555555555500000"
    "000000000000000000000000005555555555555555555500"
    "000000000000000000555540000000005555555555555500"
    "000000000000000000555540000000005555555555550000"
)


def _blocks(slots, day):
    day_slots = slots[day * 96 : (day + 1) * 96]
    blocks, start = [], 0
    for i in range(1, 97):
        if i == 96 or day_slots[i] != day_slots[start]:
            blocks.append((f"{start * 15 // 60:02d}:{start * 15 % 60:02d}", day_slots[start]))
            start = i
    return blocks


def test_decode_schedule_matches_app() -> None:
    slots = decode_schedule(CAPTURED_PROGRAMME)
    assert len(slots) == 7 * 96
    monday, friday, saturday, sunday = 0, 4, 5, 6
    assert _blocks(slots, monday) == [("00:00", "eco"), ("16:00", "comfort"), ("21:30", "eco")]
    assert _blocks(slots, friday) == [("00:00", "eco"), ("13:00", "comfort"), ("23:00", "eco")]
    assert _blocks(slots, saturday) == [
        ("00:00", "eco"),
        ("09:00", "comfort"),
        ("11:15", "eco"),
        ("16:00", "comfort"),
        ("23:00", "eco"),
    ]
    assert _blocks(slots, sunday)[-1] == ("22:00", "eco")

    assert decode_schedule("") is None
    assert decode_schedule("z" * 336) is None


def test_next_schedule_change() -> None:
    slots = decode_schedule(CAPTURED_PROGRAMME)
    tz = ZoneInfo("Europe/Amsterdam")
    monday_evening = datetime(2026, 10, 19, 18, 7, 33, tzinfo=tz)  # a Monday
    assert next_schedule_change(slots, monday_evening) == ScheduleChange(
        at=datetime(2026, 10, 19, 21, 30, tzinfo=tz), period="eco"
    )
    # Late Monday: next is Tuesday 16:00.
    assert next_schedule_change(slots, datetime(2026, 10, 19, 23, 0, tzinfo=tz)).at == datetime(
        2026, 10, 20, 16, 0, tzinfo=tz
    )
    # Sunday night wraps to Monday.
    assert next_schedule_change(slots, datetime(2026, 10, 25, 23, 0, tzinfo=tz)).at == datetime(
        2026, 10, 26, 16, 0, tzinfo=tz
    )
    # DST ends on 2026-10-25 at 03:00: the schedule follows the wall clock.
    change = next_schedule_change(slots, datetime(2026, 10, 25, 1, 0, tzinfo=tz))
    assert change.at == datetime(2026, 10, 25, 9, 0, tzinfo=tz)
    assert change.at.utcoffset() == timedelta(hours=1)

    assert next_schedule_change(("eco",) * (7 * 96), monday_evening) is None
