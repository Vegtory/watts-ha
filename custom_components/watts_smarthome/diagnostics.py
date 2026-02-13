"""Diagnostics support for Watts SmartHome."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DATA_COORDINATOR, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    # Get coordinator data
    data = coordinator.data or {}

    # Redact sensitive information
    diagnostics_data = {
        "entry": {
            "title": entry.title,
            "version": entry.version,
        },
        "coordinator_data": _redact_data(data),
    }

    return diagnostics_data


def _redact_data(data: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive information from data."""
    if not isinstance(data, dict):
        return data

    redacted = {}
    
    for key, value in data.items():
        # Redact sensitive keys
        if key in ("user_id", "email", "user_email", "mac_address", "id", "id_device"):
            redacted[key] = "**REDACTED**"
        elif key in ("latitude", "longitude", "address_position"):
            redacted[key] = "**REDACTED**"
        elif isinstance(value, dict):
            redacted[key] = _redact_data(value)
        elif isinstance(value, list):
            redacted[key] = [_redact_data(item) if isinstance(item, dict) else item for item in value]
        else:
            redacted[key] = value

    return redacted
