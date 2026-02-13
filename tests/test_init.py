"""Test initialization of the Watts SmartHome integration."""
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.watts_smarthome import async_setup_entry, async_unload_entry
from custom_components.watts_smarthome.const import DOMAIN


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="test@example.com",
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        source="user",
        options={},
        unique_id="test@example.com",
    )


@pytest.fixture
def mock_api_client():
    """Mock API client."""
    with patch(
        "custom_components.watts_smarthome.WattsApiClient"
    ) as mock_client:
        client = mock_client.return_value
        client.async_login = AsyncMock()
        yield client


@pytest.fixture
def mock_coordinator():
    """Mock coordinator."""
    with patch(
        "custom_components.watts_smarthome.WattsCoordinator"
    ) as mock_coord:
        coordinator = mock_coord.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.data = {
            "user": {"email": "test@example.com"},
            "smarthomes": {},
        }
        yield coordinator


async def test_setup_entry(hass, mock_config_entry, mock_api_client, mock_coordinator):
    """Test setting up the integration."""
    with patch(
        "custom_components.watts_smarthome.hass.config_entries.async_forward_entry_setups"
    ) as mock_forward:
        mock_forward.return_value = True
        
        result = await async_setup_entry(hass, mock_config_entry)
        
        assert result is True
        assert DOMAIN in hass.data
        assert mock_config_entry.entry_id in hass.data[DOMAIN]


async def test_unload_entry(hass, mock_config_entry):
    """Test unloading the integration."""
    # Setup the entry first
    hass.data[DOMAIN] = {mock_config_entry.entry_id: {}}
    
    with patch(
        "custom_components.watts_smarthome.hass.config_entries.async_unload_platforms"
    ) as mock_unload:
        mock_unload.return_value = True
        
        result = await async_unload_entry(hass, mock_config_entry)
        
        assert result is True
