"""Helpers to normalize and format Watts SmartHome API values."""
from __future__ import annotations

from typing import Any

WATTS_TEMPERATURE_FACTOR = 32.0
WATTS_TEMPERATURE_SENTINELS = {2124.0}

MODE_LABELS: dict[str, str] = {
    "0": "Comfort",
    "1": "Off",
    "2": "Frost Protection",
    "3": "Eco",
    "4": "Boost",
    "8": "Auto Comfort",
    "11": "Auto Eco",
    "12": "On",
    "13": "Auto",
    "14": "Disabled",
}
MODE_OPTIONS: list[str] = [MODE_LABELS[key] for key in sorted(MODE_LABELS, key=int)]


def _to_float(value: Any) -> float | None:
    """Convert input to float when possible."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def decode_temperature(value: Any) -> float | None:
    """Decode raw temperature values returned by Watts API."""
    raw_value = _to_float(value)
    if raw_value is None or raw_value in WATTS_TEMPERATURE_SENTINELS:
        return None
    return round(raw_value / WATTS_TEMPERATURE_FACTOR, 1)


def decode_setpoint(value: Any) -> float | None:
    """Decode raw setpoint values returned by Watts API."""
    raw_value = _to_float(value)
    if raw_value is None:
        return None
    return round(raw_value / WATTS_TEMPERATURE_FACTOR, 1)


def encode_setpoint(value: float) -> str:
    """Encode a Home Assistant setpoint back to Watts API format."""
    return str(int(round(value * WATTS_TEMPERATURE_FACTOR)))


def format_mode(value: Any) -> str | None:
    """Return a human-friendly label for gv_mode/nv_mode codes."""
    if value in (None, ""):
        return None
    mode_code = str(value)
    return MODE_LABELS.get(mode_code, f"Mode {mode_code}")


def mode_code_from_label(label: str) -> str | None:
    """Return API mode code from a Home Assistant select label."""
    for mode_code, mode_label in MODE_LABELS.items():
        if mode_label == label:
            return mode_code
    return None


def format_binary_state(value: Any, on_label: str, off_label: str) -> str | None:
    """Format API 0/1 state values."""
    if value in (None, ""):
        return None
    return on_label if str(value) == "1" else off_label


def device_label(device_data: dict[str, Any], fallback_id: str) -> str:
    """Pick the best available display label for a device."""
    for key in ("nom_appareil", "label_interface", "zone_label", "id_device", "id"):
        candidate = device_data.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return fallback_id
