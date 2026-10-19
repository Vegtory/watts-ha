"""Tests for entity setup and state."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.climate import ATTR_HVAC_ACTION, ATTR_PRESET_MODE, HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
import pytest

from custom_components.watts_smarthome.api import WattsAuthError, WattsConnectionError
from custom_components.watts_smarthome.const import DOMAIN

from .conftest import SMARTHOME_ID


async def test_entities_created(hass, setup_integration) -> None:
    living = hass.states.get("climate.living_room")
    assert living.state == HVACMode.AUTO
    assert living.attributes["current_temperature"] == 21.4
    assert living.attributes[ATTR_PRESET_MODE] is None
    assert living.attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE

    office = hass.states.get("climate.office")
    assert office.state == HVACMode.HEAT
    assert office.attributes[ATTR_PRESET_MODE] == "comfort"
    assert office.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING

    # Schedule: no target dial, the active period is an attribute.
    assert living.attributes[ATTR_TEMPERATURE] is None
    assert living.attributes["schedule_period"] == "comfort"
    assert living.attributes["schedule_temperature"] == 19.5
    assert living.attributes["next_period"] in ("comfort", "eco")
    next_change = datetime.fromisoformat(living.attributes["next_change"])
    assert dt_util.now() < next_change < dt_util.now() + timedelta(days=7)
    sensor = hass.states.get("sensor.living_room_next_schedule_change")
    assert datetime.fromisoformat(sensor.state) == next_change
    assert sensor.attributes["next_period"] == living.attributes["next_period"]
    # Not following the schedule: no next change.
    assert hass.states.get("sensor.office_next_schedule_change").state == "unknown"
    assert "next_change" not in hass.states.get("climate.office").attributes

    assert hass.states.get("sensor.living_room_air_temperature").state == "21.4"
    problem = hass.states.get("binary_sensor.living_room_problem")
    assert problem.state == STATE_ON
    assert problem.attributes["errors"] == ["Battery failure"]
    assert hass.states.get("binary_sensor.office_problem").state == STATE_OFF

    # Duplicates of the thermostat / problem sensor are off by default.
    entities = er.async_get(hass)
    assert entities.async_get("select.living_room_mode").disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entities.async_get("sensor.living_room_error_code").disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get("select.living_room_mode") is None
    assert hass.states.get("number.bedroom_eco_temperature").state == "18.0"
    assert hass.states.get("number.bedroom_boost_duration").state == "119"
    assert hass.states.get("binary_sensor.test_home_central_unit_connection").state == STATE_ON

    registry = dr.async_get(hass)
    hub = registry.async_get_device(identifiers={(DOMAIN, SMARTHOME_ID)})
    thermostat = registry.async_get_device(identifiers={(DOMAIN, f"{SMARTHOME_ID}_C001-000")})
    assert thermostat.via_device_id == hub.id


async def test_central_offline_sensor(hass, setup_integration, fake_client) -> None:
    fake_client.seconds_since_contact = 3600
    await setup_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.test_home_central_unit_connection").state == STATE_OFF


async def test_device_disappears(hass, setup_integration, fake_client) -> None:
    zones = fake_client.read["data"]["zones"]
    fake_client.read["data"]["zones"] = [z for z in zones if z["num_zone"] != "2"]
    fake_client.read["data"]["devices"] = [d for d in fake_client.read["data"]["devices"] if d["num_zone"] != "2"]
    await setup_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("climate.bedroom").state == STATE_UNAVAILABLE
    assert hass.states.get("climate.living_room").state == HVACMode.AUTO


async def test_set_temperature_in_schedule_is_refused(hass, setup_integration, fake_client) -> None:
    with pytest.raises(ServiceValidationError, match="Switch to Heat"):
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": "climate.living_room", ATTR_TEMPERATURE: 20.0}, blocking=True
        )
    assert fake_client.pushes == []


async def test_set_temperature_with_heat_leaves_schedule(hass, setup_integration, fake_client) -> None:
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.living_room", ATTR_TEMPERATURE: 20.0, "hvac_mode": HVACMode.HEAT},
        blocking=True,
    )
    # Heat starts in comfort; the temperature then sets the comfort setpoint.
    assert fake_client.pushes[-1]["query"]["gv_mode"] == "0"
    assert fake_client.pushes[-1]["query"]["consigne_confort"] == "680"
    state = hass.states.get("climate.living_room")
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 20.0


async def test_setup_retry_on_connection_error(hass, mock_entry, fake_client) -> None:
    from unittest.mock import patch

    fake_client.read_error = WattsConnectionError("down")
    mock_entry.add_to_hass(hass)
    with patch("custom_components.watts_smarthome.WattsApiClient", return_value=fake_client):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_auth_error_starts_reauth(hass, mock_entry, fake_client) -> None:
    from unittest.mock import patch

    fake_client.read_error = WattsAuthError("nope")
    mock_entry.add_to_hass(hass)
    with patch("custom_components.watts_smarthome.WattsApiClient", return_value=fake_client):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(flow["context"]["source"] == "reauth" for flow in hass.config_entries.flow.async_progress())


async def test_unload(hass, setup_integration) -> None:
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redacts(hass, setup_integration) -> None:
    from custom_components.watts_smarthome.diagnostics import async_get_config_entry_diagnostics

    result = await async_get_config_entry_diagnostics(hass, setup_integration)
    text = str(result)
    assert "secret" not in text
    assert "user@example.com" not in text
    assert "00:11:22:33:44:55" not in text
    assert result["smarthomes"][0]["sync"]["status"] == "idle"


async def test_schedule_entities_refresh_on_quarter_hour(hass, setup_integration) -> None:
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    before = hass.states.get("sensor.living_room_next_schedule_change").last_reported
    now = dt_util.utcnow()
    quarter = now.replace(minute=now.minute - now.minute % 15, second=1, microsecond=0) + timedelta(minutes=15)
    async_fire_time_changed(hass, quarter)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.living_room_next_schedule_change").last_reported > before
