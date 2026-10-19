"""Tests for the weekly schedule: conversion and the get/set_schedule actions."""

from __future__ import annotations

import asyncio

from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.watts_smarthome.const import DOMAIN
from custom_components.watts_smarthome.models import decode_schedule
from custom_components.watts_smarthome.schedule import (
    ScheduleError,
    build_apply_program_form,
    day_blocks_to_slots,
    encode_programme,
    merge_week,
    slots_to_week_blocks,
)

from .conftest import SMARTHOME_ID, load_fixture, programme_from_form
from .test_models import CAPTURED_PROGRAMME

LIVING = "climate.living_room"


def test_round_trip_matches_capture() -> None:
    slots = decode_schedule(CAPTURED_PROGRAMME)
    week = slots_to_week_blocks(slots)
    assert week["monday"] == [{"start": "16:00", "end": "21:30"}]
    assert week["sunday"] == [{"start": "09:00", "end": "11:15"}, {"start": "16:00", "end": "22:00"}]

    rebuilt = merge_week(None, week)
    assert encode_programme(rebuilt) == CAPTURED_PROGRAMME


def test_apply_program_form_matches_app_exactly() -> None:
    """Same fields, values and order as the Watts app sent for this schedule."""
    expected = load_fixture("apply_program_form")
    # The captured save changed Saturday 11:15 -> 11:30, so rebuild from what was sent.
    form = build_apply_program_form(decode_schedule(programme_from_form(expected)))
    assert list(form.items()) == list(expected.items())


def test_block_parsing() -> None:
    slots = day_blocks_to_slots("monday", [{"start": "22:00", "end": "00:00"}])
    assert slots[88:] == ["comfort"] * 8
    # YAML 1.1 turns unquoted 16:00 into 960 (minutes); HH:MM:SS from time pickers.
    assert day_blocks_to_slots("monday", [{"start": 960, "end": "17:00:00"}])[64:68] == ["comfort"] * 4
    assert day_blocks_to_slots("monday", [{"start": "06:00", "end": "24:00"}]).count("comfort") == 72


@pytest.mark.parametrize(
    ("blocks", "key"),
    [
        ([{"start": "6.30", "end": "08:00"}], "schedule_bad_time"),
        ([{"start": "06:10", "end": "08:00"}], "schedule_not_quarter"),
        ([{"start": "08:00", "end": "06:00"}], "schedule_end_before_start"),
        ([{"start": "06:00", "end": "09:00"}, {"start": "08:00", "end": "10:00"}], "schedule_overlap"),
        ([{"start": "06:00"}], "schedule_bad_block"),
        ([{"start": "24:00", "end": "24:00"}], "schedule_bad_time"),
    ],
)
def test_block_validation(blocks, key) -> None:
    with pytest.raises(ScheduleError) as err:
        day_blocks_to_slots("monday", blocks)
    assert err.value.key == key


def test_merge_week_rules() -> None:
    current = decode_schedule(CAPTURED_PROGRAMME)
    with pytest.raises(ScheduleError, match="schedule_bad_day"):
        merge_week(current, {"funday": []})
    with pytest.raises(ScheduleError, match="schedule_empty"):
        merge_week(current, {})
    with pytest.raises(ScheduleError, match="schedule_need_full_week"):
        merge_week(None, {"monday": []})
    merged = merge_week(current, {"monday": []})
    assert "comfort" not in merged[:96]
    assert merged[96:] == list(current[96:])


async def test_get_schedule_action(hass, setup_integration) -> None:
    response = await hass.services.async_call(
        DOMAIN, "get_schedule", {"entity_id": LIVING}, blocking=True, return_response=True
    )
    result = response[LIVING]
    assert result["schedule"]["monday"] == [{"start": "07:00", "end": "09:00"}, {"start": "17:00", "end": "22:00"}]
    assert result["schedule"]["saturday"] == [{"start": "08:00", "end": "23:00"}]
    assert result["comfort_temperature"] == 19.5
    assert result["eco_temperature"] == 18.0


async def test_set_schedule_changes_only_given_days(hass, setup_integration, fake_client) -> None:
    coordinator = setup_integration.runtime_data
    response = await hass.services.async_call(
        DOMAIN,
        "set_schedule",
        {"entity_id": LIVING, "monday": [{"start": "06:30", "end": "08:00"}], "sunday": []},
        blocking=True,
        return_response=True,
    )
    result = response[LIVING]
    assert result["changed"] is True
    assert result["previous_schedule"]["monday"] == [
        {"start": "07:00", "end": "09:00"},
        {"start": "17:00", "end": "22:00"},
    ]
    assert result["schedule"]["monday"] == [{"start": "06:30", "end": "08:00"}]
    assert result["schedule"]["sunday"] == []
    assert result["schedule"]["tuesday"] == result["previous_schedule"]["tuesday"]

    (sent,) = fake_client.programs
    assert sent["id_device"] == "C001-000"
    assert sent["form"]["program[Mon][1][start]"] == "06:30"
    assert sent["form"]["program[Sun][0]" + "[end]"] == "00:00"
    assert "check_last_connexion" in fake_client.calls or coordinator.sync_state(SMARTHOME_ID).connection_checked_at

    # Shown at once, then confirmed by reading it back (no check_failure for schedules).
    shown = await hass.services.async_call(
        DOMAIN, "get_schedule", {"entity_id": LIVING}, blocking=True, return_response=True
    )
    assert shown[LIVING]["schedule"]["monday"] == [{"start": "06:30", "end": "08:00"}]

    async with asyncio.timeout(2):
        while coordinator.has_pending(SMARTHOME_ID):
            await asyncio.sleep(0.01)
    assert "check_failure" not in fake_client.calls
    assert coordinator.sync_state(SMARTHOME_ID).status == "delivered"


async def test_set_schedule_without_change_sends_nothing(hass, setup_integration, fake_client) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "set_schedule",
        {"entity_id": LIVING, "saturday": [{"start": "08:00", "end": "23:00"}]},
        blocking=True,
        return_response=True,
    )
    assert response[LIVING]["changed"] is False
    assert fake_client.programs == []


async def test_set_schedule_invalid_input_explains(hass, setup_integration, fake_client) -> None:
    with pytest.raises(ServiceValidationError, match="monday: periods overlap at 08:00"):
        await hass.services.async_call(
            DOMAIN,
            "set_schedule",
            {"entity_id": LIVING, "monday": [{"start": "06:00", "end": "09:00"}, {"start": "08:00", "end": "10:00"}]},
            blocking=True,
        )
    assert fake_client.programs == []


async def test_unconfirmed_schedule_notifies(hass, setup_integration, fake_client) -> None:
    from homeassistant.components import persistent_notification

    coordinator = setup_integration.runtime_data
    fake_client.apply_pushes = False
    await hass.services.async_call(DOMAIN, "set_schedule", {"entity_id": LIVING, "friday": []}, blocking=True)
    async with asyncio.timeout(2):
        while coordinator.has_pending(SMARTHOME_ID):
            await asyncio.sleep(0.01)
    (notification,) = persistent_notification._async_get_or_create_notifications(hass).values()
    assert "Living room: weekly schedule" in notification["message"]


async def test_action_descriptions_for_agents(hass, setup_integration) -> None:
    from homeassistant.helpers.service import async_get_all_descriptions

    descriptions = (await async_get_all_descriptions(hass))[DOMAIN]
    assert "same format that Set schedule accepts" in descriptions["get_schedule"]["description"]
    assert "Leave the field out" in descriptions["set_schedule"]["fields"]["monday"]["description"]
