"""Diagnostics for Watts SmartHome."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import WattsConfigEntry

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "email", "user_id", "mac_address", "smarthome_id", "label"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: WattsConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    state = coordinator.data
    smarthomes = []
    if state is not None:
        for index, home in enumerate(state.smarthomes):
            sync = coordinator.sync_state(home.smarthome_id)
            home_data = asdict(home)
            home_data.pop("devices_by_id", None)
            smarthomes.append(
                {
                    "index": index,
                    "smarthome": home_data,
                    "sync": {
                        "status": sync.status,
                        "peremption_ms": sync.peremption_ms,
                        "seconds_since_contact": sync.seconds_since_contact,
                        "awaiting_confirmation": coordinator.has_pending(home.smarthome_id),
                        "last_failure": sync.last_failure,
                    },
                }
            )
    return {
        "entry": async_redact_data({"data": dict(entry.data), "options": dict(entry.options)}, TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "smarthomes": async_redact_data(smarthomes, TO_REDACT),
    }
