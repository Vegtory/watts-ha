"""Helper functions for Watts SmartHome entities."""

from __future__ import annotations

from typing import Any


def as_int(value: Any) -> int | None:
    """Convert value to int if possible."""
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> float | None:
    """Convert value to float if possible."""
    if value is None:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def raw_to_celsius(raw_value: Any) -> float | None:
    """Convert API raw temperature (fahrenheit * 10) to celsius."""
    raw = as_float(raw_value)
    if raw is None:
        return None
    fahrenheit = raw / 10.0
    celsius = (fahrenheit - 32.0) * (5.0 / 9.0)
    return round(celsius, 1)


def celsius_to_raw(celsius: float) -> int:
    """Convert celsius to API raw temperature (fahrenheit * 10)."""
    fahrenheit = (celsius * (9.0 / 5.0)) + 32.0
    return int(round(fahrenheit * 10))
