"""Tests for the command sync protocol (push -> wait -> check_failure -> confirm)."""

from __future__ import annotations

import asyncio

from homeassistant.components import persistent_notification
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest

from .conftest import SMARTHOME_ID

LIVING = "climate.living_room"
BEDROOM = "climate.bedroom"
COMMAND_STATUS = "sensor.test_home_last_command"


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


async def test_write_is_optimistic_then_verified(hass, setup_integration, fake_client) -> None:
    coordinator = setup_integration.runtime_data
    fake_client.calls.clear()

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: BEDROOM, ATTR_PRESET_MODE: "comfort"},
        blocking=True,
    )

    # Shown at once, before the cloud confirms.
    state = hass.states.get(BEDROOM)
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_PRESET_MODE] == "comfort"
    assert fake_client.pushes[-1]["query"]["gv_mode"] == "0"

    # The connection is checked before the push (it is older than the cache window
    # only on the first write, so either order is fine), then check_failure after.
    await _wait_for(lambda: "check_failure" in fake_client.calls)
    await _wait_for(lambda: not coordinator.has_pending(SMARTHOME_ID))
    await hass.async_block_till_done()
    assert hass.states.get(COMMAND_STATUS).state == "delivered"
    assert hass.states.get(BEDROOM).attributes[ATTR_PRESET_MODE] == "comfort"


async def test_quick_writes_are_merged(hass, setup_integration, fake_client) -> None:
    await asyncio.gather(
        hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: BEDROOM, ATTR_PRESET_MODE: "comfort"},
            blocking=True,
        ),
        hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: BEDROOM, ATTR_TEMPERATURE: 21.0},
            blocking=True,
        ),
    )
    assert len(fake_client.pushes) == 1
    query = fake_client.pushes[0]["query"]
    # Temperature was applied to the comfort setpoint because comfort was already queued.
    assert query["gv_mode"] == "0"
    assert query["consigne_confort"] == "698"
    assert query["consigne_manuel"] == "698"
    assert hass.states.get(BEDROOM).attributes[ATTR_TEMPERATURE] == 21.0


async def test_no_reads_inside_quiet_window(hass, setup_integration, fake_client) -> None:
    coordinator = setup_integration.runtime_data
    # Make the cloud slow: it keeps returning old values for now.
    fake_client.apply_pushes = False

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: BEDROOM, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    fake_client.calls.clear()
    await coordinator.async_refresh()
    assert "smarthome_read" not in fake_client.calls
    assert hass.states.get(BEDROOM).state == HVACMode.OFF

    # After the window, reads resume; the optimistic value survives a stale read...
    await _wait_for(lambda: "smarthome_read" in fake_client.calls)
    assert hass.states.get(BEDROOM).state == HVACMode.OFF

    # ...until the cloud catches up.
    fake_client.apply(fake_client.pushes[-1]["query"])
    await _wait_for(lambda: not coordinator.has_pending(SMARTHOME_ID))
    assert hass.states.get(BEDROOM).state == HVACMode.OFF


async def test_failed_command_reverts_and_slows_down(hass, setup_integration, fake_client) -> None:
    coordinator = setup_integration.runtime_data
    fake_client.fail_next_command = True

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: BEDROOM, ATTR_PRESET_MODE: "boost"},
        blocking=True,
    )
    assert hass.states.get(BEDROOM).attributes[ATTR_PRESET_MODE] == "boost"
    assert fake_client.pushes[-1]["peremption_ms"] == 60

    await _wait_for(lambda: coordinator.sync_state(SMARTHOME_ID).status == "failed")
    await _wait_for(lambda: hass.states.get(BEDROOM).attributes[ATTR_PRESET_MODE] == "eco")
    assert hass.states.get(COMMAND_STATUS).state == "failed"

    # The user is told what was not applied.
    notifications = persistent_notification._async_get_or_create_notifications(hass)
    (notification,) = notifications.values()
    assert "Bedroom: mode Boost, boost temperature" in notification["message"]

    # The next command gets a longer window, and success resets it.
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: BEDROOM, ATTR_PRESET_MODE: "comfort"},
        blocking=True,
    )
    assert fake_client.pushes[-1]["peremption_ms"] == 80
    await _wait_for(lambda: coordinator.sync_state(SMARTHOME_ID).status == "delivered")
    assert coordinator.sync_state(SMARTHOME_ID).peremption_ms == 60
    # A delivered command clears the notice.
    assert persistent_notification._async_get_or_create_notifications(hass) == {}


async def test_offline_central_refuses_command(hass, setup_integration, fake_client) -> None:
    coordinator = setup_integration.runtime_data
    fake_client.seconds_since_contact = 600
    coordinator.sync_state(SMARTHOME_ID).connection_checked_at = None

    with pytest.raises(HomeAssistantError, match="600 seconds"):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: BEDROOM, ATTR_PRESET_MODE: "comfort"},
            blocking=True,
        )
    assert fake_client.pushes == []
    # Optimistic state rolled back.
    assert hass.states.get(BEDROOM).attributes[ATTR_PRESET_MODE] == "eco"


async def test_holiday_mode_blocks_writes(hass, setup_integration, fake_client) -> None:
    coordinator = setup_integration.runtime_data
    fake_client.read["data"]["holiday_start"] = "2000-01-01 00:00:00"
    fake_client.read["data"]["holiday_end"] = "2999-01-01 00:00:00"
    await coordinator.async_refresh()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: BEDROOM, ATTR_TEMPERATURE: 20.0},
            blocking=True,
        )
    assert fake_client.pushes == []


async def test_user_list_is_not_reloaded_every_poll(hass, setup_integration, fake_client) -> None:
    coordinator = setup_integration.runtime_data
    fake_client.calls.clear()
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert fake_client.calls.count("smarthome_read") == 2
    assert "user_read" not in fake_client.calls


async def test_back_to_back_commands_share_one_check(hass, setup_integration, fake_client) -> None:
    coordinator = setup_integration.runtime_data
    fake_client.calls.clear()
    for entity_id in (BEDROOM, LIVING):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "eco" if entity_id == LIVING else "comfort"},
            blocking=True,
        )
    assert fake_client.calls.count("push") == 2
    await _wait_for(lambda: coordinator.sync_state(SMARTHOME_ID).status == "delivered")
    await _wait_for(lambda: not coordinator.has_pending(SMARTHOME_ID))
    assert fake_client.calls.count("check_failure") == 1
    assert hass.states.get(LIVING).attributes[ATTR_PRESET_MODE] == "eco"


async def test_unknown_check_result_confirmed_by_read(hass, setup_integration, fake_client) -> None:
    from custom_components.watts_smarthome.api import WattsConnectionError

    coordinator = setup_integration.runtime_data

    async def broken_check(*args, **kwargs):
        raise WattsConnectionError("timeout")

    fake_client.async_check_query_failure = broken_check
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: BEDROOM, ATTR_PRESET_MODE: "comfort"},
        blocking=True,
    )
    assert coordinator.sync_state(SMARTHOME_ID).status == "sent"
    await _wait_for(lambda: coordinator.sync_state(SMARTHOME_ID).status == "delivered")


async def test_unconfirmed_change_notifies(hass, setup_integration, fake_client) -> None:
    coordinator = setup_integration.runtime_data
    fake_client.apply_pushes = False  # the thermostat never reports the new value

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: BEDROOM, ATTR_TEMPERATURE: 19.0},
        blocking=True,
    )
    await _wait_for(lambda: not coordinator.has_pending(SMARTHOME_ID))
    notifications = persistent_notification._async_get_or_create_notifications(hass)
    (notification,) = notifications.values()
    assert "still reports its old settings" in notification["message"]
    assert "Bedroom: mode Eco, eco temperature 19.0 °C" in notification["message"]
    # The view falls back to what the cloud reports.
    assert hass.states.get(BEDROOM).attributes[ATTR_TEMPERATURE] == 18.0
