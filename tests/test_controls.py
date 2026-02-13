"""Tests for selector/control helpers."""

from custom_components.watts_smarthome import _resolve_program_device_id
from custom_components.watts_smarthome.select import (
    MODE_CODE_TO_LABEL,
    MODE_LABEL_TO_CODE,
    _normalize_mode_code,
)


def test_mode_selector_includes_frost_mode() -> None:
    """Mode mappings should expose frost mode and resolve aliases."""
    assert MODE_LABEL_TO_CODE["Frost"] == "2"
    assert MODE_CODE_TO_LABEL["2"] == "Frost"
    assert _normalize_mode_code("14") == "1"
    assert _normalize_mode_code("13") == "8"


def test_resolve_program_device_id_short_and_full() -> None:
    """Program service should accept short IDs and normalize to full IDs."""

    class DummyCoordinator:
        data = {
            "smarthomes": {
                "smarthome-1": {
                    "devices": [
                        {
                            "id": "smarthome-1#C001-000",
                            "id_device": "C001-000",
                        }
                    ]
                }
            }
        }

    coordinator = DummyCoordinator()

    assert (
        _resolve_program_device_id(coordinator, "C001-000")
        == "smarthome-1#C001-000"
    )
    assert (
        _resolve_program_device_id(coordinator, "smarthome-1#C001-000")
        == "smarthome-1#C001-000"
    )
    assert _resolve_program_device_id(coordinator, "unknown-device") == "unknown-device"
