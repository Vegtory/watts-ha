"""Tests for the Watts SmartHome config flow."""
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.watts_smarthome.api import WattsAuthError
from custom_components.watts_smarthome.const import DOMAIN


@pytest.fixture
def mock_api_client():
    """Mock API client."""
    with patch(
        "custom_components.watts_smarthome.config_flow.WattsApiClient"
    ) as mock_client:
        client = mock_client.return_value
        client.async_login = AsyncMock()
        client.async_get_user_data = AsyncMock(
            return_value={
                "data": {
                    "email": "test@example.com",
                    "smarthomes": [],
                }
            }
        )
        yield client


async def test_form_shown(hass):
    """Test that the form is served."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_successful_config(hass, mock_api_client):
    """Test successful configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "test@example.com"
    assert result["data"][CONF_USERNAME] == "test@example.com"


async def test_invalid_auth(hass, mock_api_client):
    """Test invalid authentication."""
    mock_api_client.async_login.side_effect = WattsAuthError("Invalid credentials")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "wrongpassword",
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_duplicate_entry(hass, mock_api_client):
    """Test that duplicate entries are prevented."""
    # Create first entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    # Try to create duplicate
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
