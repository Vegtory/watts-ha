"""Weekly schedule conversion: readable blocks <-> Watts programme formats.

Readable format (used by the get/set_schedule actions):

    {"monday": [{"start": "16:00", "end": "21:30"}], "tuesday": [], ...}

Listed blocks run at the comfort temperature, all other times at eco.
Times are HH:MM in 15-minute steps; "00:00" or "24:00" as end means midnight.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .const import MODE_COMFORT, MODE_ECO
from .models import SCHEDULE_SLOT_MINUTES, SCHEDULE_SLOTS_PER_WEEK

DAYS: tuple[str, ...] = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
SLOTS_PER_DAY = SCHEDULE_SLOTS_PER_WEEK // 7
# device/apply_program uses English day abbreviations, Sunday first (as the app sends them).
_APP_DAY_ORDER: tuple[tuple[str, int], ...] = (
    ("Sun", 6),
    ("Mon", 0),
    ("Tue", 1),
    ("Wed", 2),
    ("Thu", 3),
    ("Fri", 4),
    ("Sat", 5),
)
_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_BITS = {MODE_ECO: 0, MODE_COMFORT: 1}


class ScheduleError(ValueError):
    """Invalid schedule input; `key`/`placeholders` map to a translated message."""

    def __init__(self, key: str, **placeholders: str) -> None:
        super().__init__(f"{key}: {placeholders}")
        self.key = key
        self.placeholders = placeholders


def _format_minutes(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_time(value: Any, *, day: str, is_end: bool) -> int:
    """Parse "HH:MM" (or "HH:MM:SS") to minutes since midnight.

    YAML 1.1 reads an unquoted 16:00 as the number 960 (base 60), which is exactly
    the minutes since midnight, so plain integers are accepted as minutes.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        total = value
    else:
        match = _TIME.match(str(value).strip())
        if not match or (match.group(3) not in (None, "00")) or int(match.group(2)) >= 60:
            raise ScheduleError("schedule_bad_time", day=day, time=str(value))
        total = int(match.group(1)) * 60 + int(match.group(2))
    if total < 0 or total > 24 * 60 or (total == 24 * 60 and not is_end):
        raise ScheduleError("schedule_bad_time", day=day, time=str(value))
    if total % SCHEDULE_SLOT_MINUTES:
        raise ScheduleError("schedule_not_quarter", day=day, time=_format_minutes(total))
    if is_end and total == 0:
        total = 24 * 60
    return total


def day_blocks_to_slots(day: str, blocks: Sequence[Mapping[str, Any]]) -> list[str]:
    """Convert one day's comfort blocks to 96 period slots; raises ScheduleError."""
    slots = [MODE_ECO] * SLOTS_PER_DAY
    for block in blocks:
        if not isinstance(block, Mapping) or "start" not in block or "end" not in block:
            raise ScheduleError("schedule_bad_block", day=day)
        start = _parse_time(block["start"], day=day, is_end=False)
        end = _parse_time(block["end"], day=day, is_end=True)
        if end <= start:
            raise ScheduleError("schedule_end_before_start", day=day, start=str(block["start"]), end=str(block["end"]))
        for slot in range(start // SCHEDULE_SLOT_MINUTES, end // SCHEDULE_SLOT_MINUTES):
            if slots[slot] == MODE_COMFORT:
                raise ScheduleError("schedule_overlap", day=day, time=_format_minutes(slot * SCHEDULE_SLOT_MINUTES))
            slots[slot] = MODE_COMFORT
    return slots


def slots_to_week_blocks(slots: Sequence[str]) -> dict[str, list[dict[str, str]]]:
    """Convert 672 period slots to readable comfort blocks per day."""
    week: dict[str, list[dict[str, str]]] = {}
    for day_index, day in enumerate(DAYS):
        day_slots = slots[day_index * SLOTS_PER_DAY : (day_index + 1) * SLOTS_PER_DAY]
        blocks: list[dict[str, str]] = []
        start: int | None = None
        for slot in range(SLOTS_PER_DAY + 1):
            comfort = slot < SLOTS_PER_DAY and day_slots[slot] == MODE_COMFORT
            if comfort and start is None:
                start = slot
            elif not comfort and start is not None:
                blocks.append(
                    {
                        "start": _format_minutes(start * SCHEDULE_SLOT_MINUTES),
                        "end": _format_minutes(slot * SCHEDULE_SLOT_MINUTES),
                    }
                )
                start = None
        week[day] = blocks
    return week


def merge_week(current: Sequence[str] | None, changes: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[str]:
    """Return the full week of slots: changed days from `changes`, the rest from `current`."""
    unknown = [day for day in changes if day not in DAYS]
    if unknown:
        raise ScheduleError("schedule_bad_day", day=", ".join(unknown))
    if not changes:
        raise ScheduleError("schedule_empty")
    if current is None and len(changes) < len(DAYS):
        raise ScheduleError("schedule_need_full_week")

    week: list[str] = list(current) if current is not None else [MODE_ECO] * SCHEDULE_SLOTS_PER_WEEK
    for day_index, day in enumerate(DAYS):
        if day in changes:
            week[day_index * SLOTS_PER_DAY : (day_index + 1) * SLOTS_PER_DAY] = day_blocks_to_slots(day, changes[day])
    return week


def encode_programme(slots: Sequence[str]) -> str:
    """Encode 672 slots to the 336-character programme string smarthome/read returns."""
    if len(slots) != SCHEDULE_SLOTS_PER_WEEK:
        raise ValueError("A schedule has 672 slots")
    chars = []
    for i in range(0, SCHEDULE_SLOTS_PER_WEEK, 2):
        chars.append(f"{(_BITS.get(slots[i], 0) << 2) | _BITS.get(slots[i + 1], 0):x}")
    return "".join(chars)


def build_apply_program_form(slots: Sequence[str]) -> dict[str, str]:
    """Build the program[...] form fields for device/apply_program (as the app sends them)."""
    if any(slot not in _BITS for slot in slots):
        # The app can only send comfort/eco periods; refuse instead of silently changing others.
        raise ScheduleError("schedule_unsupported_period")
    form: dict[str, str] = {}
    for app_day, day_index in _APP_DAY_ORDER:
        day_slots = slots[day_index * SLOTS_PER_DAY : (day_index + 1) * SLOTS_PER_DAY]
        segment, start = 0, 0
        for slot in range(1, SLOTS_PER_DAY + 1):
            if slot == SLOTS_PER_DAY or day_slots[slot] != day_slots[start]:
                prefix = f"program[{app_day}][{segment}]"
                form[f"{prefix}[start]"] = _format_minutes(start * SCHEDULE_SLOT_MINUTES)
                form[f"{prefix}[end]"] = _format_minutes(slot * SCHEDULE_SLOT_MINUTES)
                form[f"{prefix}[value]"] = "comfort" if day_slots[start] == MODE_COMFORT else "false"
                segment += 1
                start = slot
    return form
