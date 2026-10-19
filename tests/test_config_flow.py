"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.watts_smarthome.api import WattsAuthError, WattsConnectionError
from custom_components.watts_smarthome.const import CONF_LANG, CONF_SCAN_INTERVAL, DOMAIN

CLIENT = "custom_components.watts_smarthome.config_flow.WattsApiClient"
SETUP_CLIENT = "custom_components.watts_smarthome.WattsApiClient"


async def test_user_flow(hass, fake_client) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    with patch(CLIENT, return_value=fake_client), patch(SETUP_CLIENT, return_value=fake_client):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: " user@example.com ", CONF_PASSWORD: "secret"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@example.com"
    assert result["data"] == {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"}
    assert result["result"].unique_id == "42"


async def test_user_flow_errors_then_recovers(hass, fake_client) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    for error, key in (
        (WattsAuthError("x"), "invalid_auth"),
        (WattsConnectionError("x"), "cannot_connect"),
        (RuntimeError(), "unknown"),
    ):
        fake_client.login_error = error
        with patch(CLIENT, return_value=fake_client):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "bad"}
            )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": key}

    fake_client.login_error = None
    with patch(CLIENT, return_value=fake_client), patch(SETUP_CLIENT, return_value=fake_client):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_account_aborts(hass, mock_entry, fake_client) -> None:
    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(CLIENT, return_value=fake_client):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(hass, setup_integration, fake_client) -> None:
    result = await setup_integration.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    fake_client.login_error = WattsAuthError("x")
    with patch(CLIENT, return_value=fake_client):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}

    fake_client.login_error = None
    with patch(CLIENT, return_value=fake_client), patch(SETUP_CLIENT, return_value=fake_client):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "new"})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert setup_integration.data[CONF_PASSWORD] == "new"


async def test_reconfigure_flow(hass, setup_integration, fake_client) -> None:
    result = await setup_integration.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch(CLIENT, return_value=fake_client), patch(SETUP_CLIENT, return_value=fake_client):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "changed"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert setup_integration.data[CONF_PASSWORD] == "changed"


async def test_options_flow(hass, setup_integration, fake_client) -> None:
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    with patch(SETUP_CLIENT, return_value=fake_client):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_LANG: "nl_NL", CONF_SCAN_INTERVAL: 120}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_integration.options == {CONF_LANG: "nl_NL", CONF_SCAN_INTERVAL: 120}
