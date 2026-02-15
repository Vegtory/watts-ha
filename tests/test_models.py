"""Tests for Watts domain model parsing and write payload builders."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.watts_smarthome.const import MODE_BOOST, SETPOINT_ANTI_FROST, SETPOINT_COMFORT
from custom_components.watts_smarthome.models import (
    build_boost_timer_write_request,
    build_mode_write_request,
    build_setpoint_write_request,
    celsius_to_raw,
    parse_state,
)


def _load_response(suffix: str) -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    files = sorted((repo_root / ".responses").glob(f"*{suffix}.json"))
    assert files, f"No response fixture found for suffix: {suffix}"
    return json.loads(files[-1].read_text(encoding="utf-8"))


def test_parse_state_maps_devices_and_errors() -> None:
    """State parsing should map all devices and attach error details."""
    user_payload = _load_response("_user_read")
    smarthome_payload = _load_response("_smarthome_MDA6MUU6QzA6NUI6RTk6NEQ_e_read")
    error_payload = _load_response("_smarthome_MDA6MUU6QzA6NUI6RTk6NEQ_e_get_errors")

    smarthome_id = user_payload["data"]["smarthomes"][0]["smarthome_id"]

    state = parse_state(
        user_payload=user_payload,
        smarthome_payloads={smarthome_id: smarthome_payload},
        smarthome_error_payloads={smarthome_id: error_payload},
    )

    assert state.user.email == "w.j.vegt@gmail.com"
    assert len(state.smarthomes) == 1

    device = state.get_device(smarthome_id, "C001-000")
    assert device.current_air_temperature == 21.4
    assert device.current_mode == "manual"
    assert device.get_setpoint(SETPOINT_ANTI_FROST) == 7.0
    assert device.min_set_point == 5.0
    assert device.max_set_point == 37.0

    errored = state.get_device(smarthome_id, "C004-003")
    assert errored.current_mode == "eco"
    assert len(errored.errors) == 2
    assert errored.errors[0].code == "P_RF"


def test_write_requests_build_expected_query_payloads() -> None:
    """Write requests should encode expected query fields."""
    user_payload = _load_response("_user_read")
    smarthome_payload = _load_response("_smarthome_MDA6MUU6QzA6NUI6RTk6NEQ_e_read")
    smarthome_id = user_payload["data"]["smarthomes"][0]["smarthome_id"]

    state = parse_state(
        user_payload=user_payload,
        smarthome_payloads={smarthome_id: smarthome_payload},
        smarthome_error_payloads={},
    )

    device = state.get_device(smarthome_id, "C001-000")

    mode_request = build_mode_write_request(device=device, selected_mode=MODE_BOOST)
    assert mode_request.query["id_device"] == "C001-000"
    assert mode_request.query["gv_mode"] == "4"
    assert mode_request.query["nv_mode"] == "4"

    setpoint_request = build_setpoint_write_request(
        device=device,
        setpoint_key=SETPOINT_COMFORT,
        value_celsius=21.5,
    )
    assert setpoint_request.query[SETPOINT_COMFORT] == str(celsius_to_raw(21.5))
    assert setpoint_request.query["id_device"] == "C001-000"

    timer_request = build_boost_timer_write_request(device=device, value_seconds=1800)
    assert timer_request.query["time_boost"] == "1800"
