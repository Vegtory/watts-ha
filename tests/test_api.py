"""Tests for the Watts SmartHome API client."""
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.watts_smarthome.api import (
    WattsApiClient,
    WattsApiError,
    WattsAuthError,
)


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session."""
    session = MagicMock(spec=aiohttp.ClientSession)
    return session


@pytest.fixture
def api_client(mock_session):
    """Create an API client with mocked session."""
    return WattsApiClient(
        username="test@example.com",
        password="testpassword",
        session=mock_session,
    )


@pytest.mark.asyncio
async def test_login_success(api_client, mock_session):
    """Test successful login."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 300,
        }
    )
    
    mock_session.post = AsyncMock(return_value=mock_response)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    result = await api_client.async_login()

    assert result["access_token"] == "test_access_token"
    assert result["refresh_token"] == "test_refresh_token"
    assert api_client._access_token == "test_access_token"
    assert api_client._refresh_token == "test_refresh_token"


@pytest.mark.asyncio
async def test_login_invalid_credentials(api_client, mock_session):
    """Test login with invalid credentials."""
    mock_response = AsyncMock()
    mock_response.status = 401
    
    mock_session.post = AsyncMock(return_value=mock_response)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with pytest.raises(WattsAuthError):
        await api_client.async_login()


@pytest.mark.asyncio
async def test_get_user_data(api_client, mock_session):
    """Test getting user data."""
    # Setup login
    api_client._access_token = "test_token"
    api_client._token_expires = None

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "code": {"code": "200", "key": "success", "value": "OK"},
            "data": {
                "email": "test@example.com",
                "smarthomes": [],
            },
        }
    )
    
    mock_session.request = AsyncMock(return_value=mock_response)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    result = await api_client.async_get_user_data()

    assert result["data"]["email"] == "test@example.com"
    assert "smarthomes" in result["data"]


@pytest.mark.asyncio
async def test_token_refresh(api_client, mock_session):
    """Test token refresh."""
    api_client._refresh_token = "old_refresh_token"

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 300,
        }
    )
    
    mock_session.post = AsyncMock(return_value=mock_response)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    result = await api_client.async_refresh_token()

    assert result["access_token"] == "new_access_token"
    assert api_client._access_token == "new_access_token"
