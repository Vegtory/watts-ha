"""API client for Watts SmartHome."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

import aiohttp
from aiohttp import ClientError, ClientTimeout

from .const import (
    API_BASE_URL,
    CLIENT_ID,
    ENDPOINT_APPLY_PROGRAM,
    ENDPOINT_CHECK_LAST_CONNEXION,
    ENDPOINT_CONVERT_PROGRAM,
    ENDPOINT_GET_ERRORS,
    ENDPOINT_QUERY_PUSH,
    ENDPOINT_SMARTHOME_READ,
    ENDPOINT_TIME_OFFSET,
    ENDPOINT_USER_READ,
    GRANT_TYPE_PASSWORD,
    GRANT_TYPE_REFRESH,
    TOKEN_ENDPOINT,
    DEFAULT_LANG,
)

_LOGGER = logging.getLogger(__name__)

# Timeout for API requests
API_TIMEOUT = ClientTimeout(total=30)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds


class WattsApiError(Exception):
    """Base exception for Watts API errors."""


class WattsAuthError(WattsApiError):
    """Exception for authentication errors."""


class WattsApiClient:
    """API client for Watts SmartHome."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the API client."""
        self._username = username
        self._password = password
        self._session = session
        self._own_session = session is None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires: datetime | None = None
        self._lock = asyncio.Lock()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure we have an aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=API_TIMEOUT)
        return self._session

    async def close(self) -> None:
        """Close the API client session."""
        if self._own_session and self._session:
            await self._session.close()
            self._session = None

    async def async_login(self) -> dict[str, Any]:
        """Authenticate using password grant and return token data."""
        session = await self._ensure_session()

        data = {
            "grant_type": GRANT_TYPE_PASSWORD,
            "username": self._username,
            "password": self._password,
            "client_id": CLIENT_ID,
        }

        _LOGGER.debug("Authenticating with Watts SmartHome API")

        try:
            async with session.post(
                TOKEN_ENDPOINT,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status == 401:
                    raise WattsAuthError("Invalid username or password")
                if response.status != 200:
                    text = await response.text()
                    raise WattsApiError(
                        f"Authentication failed with status {response.status}: {text}"
                    )

                token_data = await response.json()
                self._access_token = token_data.get("access_token")
                self._refresh_token = token_data.get("refresh_token")
                
                expires_in = token_data.get("expires_in", 300)
                self._token_expires = datetime.now() + timedelta(seconds=expires_in - 60)
                
                _LOGGER.debug("Successfully authenticated")
                return token_data

        except ClientError as err:
            raise WattsApiError(f"Network error during authentication: {err}") from err

    async def async_refresh_token(self) -> dict[str, Any]:
        """Refresh the access token using refresh token."""
        if not self._refresh_token:
            _LOGGER.debug("No refresh token available, performing login")
            return await self.async_login()

        session = await self._ensure_session()

        data = {
            "grant_type": GRANT_TYPE_REFRESH,
            "refresh_token": self._refresh_token,
            "client_id": CLIENT_ID,
        }

        _LOGGER.debug("Refreshing access token")

        try:
            async with session.post(
                TOKEN_ENDPOINT,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status in (401, 403):
                    _LOGGER.debug("Refresh token expired, performing login")
                    return await self.async_login()
                
                if response.status != 200:
                    text = await response.text()
                    _LOGGER.warning(
                        "Token refresh failed with status %s, performing login", 
                        response.status
                    )
                    return await self.async_login()

                token_data = await response.json()
                self._access_token = token_data.get("access_token")
                self._refresh_token = token_data.get("refresh_token", self._refresh_token)
                
                expires_in = token_data.get("expires_in", 300)
                self._token_expires = datetime.now() + timedelta(seconds=expires_in - 60)
                
                _LOGGER.debug("Successfully refreshed token")
                return token_data

        except ClientError as err:
            _LOGGER.warning("Network error during token refresh: %s", err)
            return await self.async_login()

    async def _ensure_token(self) -> None:
        """Ensure we have a valid access token."""
        async with self._lock:
            if not self._access_token or (
                self._token_expires and datetime.now() >= self._token_expires
            ):
                await self.async_refresh_token()

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        retry: int = 0,
    ) -> dict[str, Any]:
        """Make an authenticated API request."""
        await self._ensure_token()
        session = await self._ensure_session()

        headers = {"Authorization": f"Bearer {self._access_token}"}
        
        request_data = data
        if data and self._access_token:
            # Add token to form data for endpoints that expect it
            request_data = {**data, "token": self._access_token}

        url = f"{API_BASE_URL}{endpoint}"

        try:
            async with session.request(
                method,
                url,
                data=request_data,
                json=json_data,
                headers=headers,
            ) as response:
                if response.status in (401, 403):
                    if retry < MAX_RETRIES:
                        _LOGGER.debug("Got %s, refreshing token and retrying", response.status)
                        await self.async_refresh_token()
                        return await self._request(method, endpoint, data, json_data, retry + 1)
                    raise WattsAuthError("Authentication failed after retries")

                if response.status != 200:
                    text = await response.text()
                    raise WattsApiError(
                        f"API request failed with status {response.status}: {text}"
                    )

                return await response.json()

        except ClientError as err:
            if retry < MAX_RETRIES:
                _LOGGER.debug("Network error, retrying: %s", err)
                await asyncio.sleep(RETRY_DELAY * (retry + 1))
                return await self._request(method, endpoint, data, json_data, retry + 1)
            raise WattsApiError(f"Network error: {err}") from err

    async def async_get_user_data(self, lang: str = DEFAULT_LANG) -> dict[str, Any]:
        """Get user profile and smarthomes."""
        data = {"lang": lang}
        return await self._request("POST", ENDPOINT_USER_READ, data=data)

    async def async_get_smarthome_data(
        self, smarthome_id: str, lang: str = DEFAULT_LANG
    ) -> dict[str, Any]:
        """Get smarthome state including zones and devices."""
        data = {"smarthome_id": smarthome_id, "lang": lang}
        return await self._request("POST", ENDPOINT_SMARTHOME_READ, data=data)

    async def async_get_errors(
        self, smarthome_id: str, lang: str = DEFAULT_LANG
    ) -> dict[str, Any]:
        """Get smarthome errors."""
        data = {"smarthome_id": smarthome_id, "lang": lang}
        return await self._request("POST", ENDPOINT_GET_ERRORS, data=data)

    async def async_check_last_connection(
        self, smarthome_id: str, lang: str = DEFAULT_LANG
    ) -> dict[str, Any]:
        """Check last connection time for a smarthome."""
        data = {"smarthome_id": smarthome_id, "lang": lang}
        return await self._request("POST", ENDPOINT_CHECK_LAST_CONNEXION, data=data)

    async def async_get_time_offset(
        self, smarthome_id: str, lang: str = DEFAULT_LANG
    ) -> dict[str, Any]:
        """Get smarthome time offset."""
        data = {"smarthome_id": smarthome_id, "lang": lang}
        return await self._request("POST", ENDPOINT_TIME_OFFSET, data=data)

    async def async_apply_program(
        self,
        device_id: str,
        program_data: dict[str, Any],
        lang: str = DEFAULT_LANG,
    ) -> dict[str, Any]:
        """Apply a weekly program to a device."""
        data = {
            "device_id": device_id,
            "lang": lang,
            **program_data,
        }
        return await self._request("POST", ENDPOINT_APPLY_PROGRAM, data=data)

    async def async_convert_program(
        self,
        program_data: dict[str, Any],
        lang: str = DEFAULT_LANG,
    ) -> dict[str, Any]:
        """Convert device program into UI-friendly blocks."""
        data = {"lang": lang, **program_data}
        return await self._request("POST", ENDPOINT_CONVERT_PROGRAM, data=data)

    async def async_push_query(
        self,
        smarthome_id: str,
        query_data: dict[str, Any],
        lang: str = DEFAULT_LANG,
    ) -> dict[str, Any]:
        """Send a command/query to a device."""
        data = {
            "smarthome_id": smarthome_id,
            "lang": lang,
            **query_data,
        }
        return await self._request("POST", ENDPOINT_QUERY_PUSH, data=data)
