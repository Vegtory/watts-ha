"""Tests for Watts payload formatting helpers."""
from custom_components.watts_smarthome.formatting import (
    decode_setpoint,
    decode_temperature,
    device_label,
    encode_setpoint,
    format_mode,
    mode_code_from_label,
)


def test_decode_temperature() -> None:
    """Temperatures are raw fixed-point values and include sentinel values."""
    assert decode_temperature("624") == 19.5
    assert decode_temperature(692) == 21.6
    assert decode_temperature("2124") is None
    assert decode_temperature(None) is None


def test_decode_and_encode_setpoint() -> None:
    """Setpoints should round-trip between HA and API formats."""
    assert decode_setpoint("590") == 18.4
    assert encode_setpoint(19.5) == "624"
    assert encode_setpoint(21.8) == "698"


def test_mode_mapping() -> None:
    """Known modes should map to friendly labels and back."""
    assert format_mode("8") == "Auto Comfort"
    assert format_mode("14") == "Disabled"
    assert format_mode("99") == "Mode 99"
    assert mode_code_from_label("Auto Comfort") == "8"
    assert mode_code_from_label("Eco") == "3"
    assert mode_code_from_label("Unsupported") is None


def test_device_label_resolution() -> None:
    """Device names should fall back through known label fields."""
    assert (
        device_label({"nom_appareil": "Living Room", "id_device": "C001-000"}, "C001-000")
        == "Living Room"
    )
    assert (
        device_label({"label_interface": "Kitchen", "id_device": "C002-001"}, "C002-001")
        == "Kitchen"
    )
    assert device_label({"zone_label": "Hall"}, "C003-002") == "Hall"
    assert device_label({"id_device": "C004-003"}, "fallback") == "C004-003"
    assert device_label({}, "fallback") == "fallback"
