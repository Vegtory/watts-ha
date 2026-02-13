"""Helpers for Watts weekly program payload formatting."""
from __future__ import annotations

from typing import Any

DAY_ALIASES = {
    "monday": "monday",
    "mon": "monday",
    "tuesday": "tuesday",
    "tue": "tuesday",
    "wednesday": "wednesday",
    "wed": "wednesday",
    "thursday": "thursday",
    "thu": "thursday",
    "friday": "friday",
    "fri": "friday",
    "saturday": "saturday",
    "sat": "saturday",
    "sunday": "sunday",
    "sun": "sunday",
}


def _normalize_day(day: str) -> str:
    """Normalize day names to API-compatible keys."""
    return DAY_ALIASES.get(day.strip().lower(), day.strip().lower())


def normalize_program_data(program_data: dict[str, Any]) -> dict[str, Any]:
    """Convert structured weekly programs into flattened API form fields.

    Accepted input formats:
    - Existing flattened API format:
      {"program[monday][0][start]": "06:00", ...}
    - Structured format:
      {
        "program": {
          "monday": [{"start": "06:00", "end": "08:00", "value": "comfort"}],
          "tuesday": [...],
        }
      }
      or without wrapper:
      {
        "monday": [{"start": "06:00", "end": "08:00", "value": "comfort"}]
      }
    """
    if any(key.startswith("program[") for key in program_data):
        return dict(program_data)

    source = program_data.get("program", program_data)
    if not isinstance(source, dict):
        return dict(program_data)

    normalized: dict[str, Any] = {}
    passthrough = {
        key: value
        for key, value in program_data.items()
        if key != "program"
    }
    normalized.update(passthrough)

    for raw_day, blocks in source.items():
        if not isinstance(raw_day, str) or not isinstance(blocks, list):
            continue

        day = _normalize_day(raw_day)
        for index, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue

            start = block.get("start")
            end = block.get("end")
            value = block.get("value", block.get("mode"))
            if start in (None, "") or end in (None, "") or value in (None, ""):
                continue

            normalized[f"program[{day}][{index}][start]"] = str(start)
            normalized[f"program[{day}][{index}][end]"] = str(end)
            normalized[f"program[{day}][{index}][value]"] = str(value)

    return normalized
