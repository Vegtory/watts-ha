"""Tests for weekly program normalization helpers."""
from custom_components.watts_smarthome.program import normalize_program_data


def test_keep_flattened_program_data() -> None:
    """Flattened API payloads should be passed through unchanged."""
    payload = {
        "program[monday][0][start]": "06:00",
        "program[monday][0][end]": "08:00",
        "program[monday][0][value]": "comfort",
    }
    assert normalize_program_data(payload) == payload


def test_normalize_structured_program_data() -> None:
    """Structured weekly schedules should be flattened for API calls."""
    payload = {
        "program": {
            "monday": [
                {"start": "06:00", "end": "08:00", "value": "comfort"},
                {"start": "08:00", "end": "23:00", "mode": "eco"},
            ],
            "tue": [
                {"start": "06:30", "end": "09:00", "value": "comfort"},
            ],
        }
    }
    normalized = normalize_program_data(payload)

    assert normalized["program[monday][0][start]"] == "06:00"
    assert normalized["program[monday][0][end]"] == "08:00"
    assert normalized["program[monday][0][value]"] == "comfort"
    assert normalized["program[monday][1][value]"] == "eco"
    assert normalized["program[tuesday][0][start]"] == "06:30"


def test_normalize_structured_program_data_with_passthrough() -> None:
    """Non-program keys should be preserved when flattening."""
    payload = {
        "timezone": "Europe/Amsterdam",
        "program": {
            "sunday": [
                {"start": "00:00", "end": "24:00", "value": "eco"},
            ]
        },
    }
    normalized = normalize_program_data(payload)

    assert normalized["timezone"] == "Europe/Amsterdam"
    assert normalized["program[sunday][0][value]"] == "eco"
