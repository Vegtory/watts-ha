"""Async API client for the Watts SmartHome cloud endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
import logging
import time
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    AUTH_BASE_URL,
    DEFAULT_LANG,
    REQUEST_CONTEXT,
    REQUEST_PEREMPTION_MS,
    REQUEST_TOKEN_LITERAL,
    TOKEN_CLIENT_ID,
    TOKEN_GRANT_TYPE,
    TOKEN_PATH,
)

_LOGGER = logging.getLogger(__name__)

_SUCCESS_CODES = {"1", "8"}


class WattsError(Exception):
    """Base error for Watts integration."""


class WattsConnectionError(WattsError):
    """Raised when the remote endpoint cannot be reached."""


class WattsAuthError(WattsError):
    """Raised when authentication fails."""


class WattsApiError(WattsError):
    """Raised when API returns an error payload."""


@dataclass(slots=True)
class WattsToken:
    """OAuth token metadata."""

    access_token: str
    refresh_token: str
    expires_at: float


class WattsApiClient:
    """Async client for Watts auth and API endpoints."""

    def __init__(
        self,
        *,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        default_lang: str = DEFAULT_LANG,
        request_timeout: float = 20,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._default_lang = default_lang
        self._request_timeout = request_timeout
        self._token: WattsToken | None = None

        # Compatibility fields consumed by local scripts.
        self._access_token: str | None = None
        self._refresh_token: str | None = None

    async def async_login(self) -> dict[str, Any]:
        """Authenticate with username/password and cache token."""
        payload = {
            "grant_type": TOKEN_GRANT_TYPE,
            "username": self._username,
            "password": self._password,
            "client_id": TOKEN_CLIENT_ID,
        }

        status, response = await self._async_raw_request(
            "POST",
            f"{AUTH_BASE_URL}{TOKEN_PATH}",
            data=payload,
        )

        if status >= 400:
            raise WattsAuthError(f"Watts authentication failed with HTTP {status}")

        access_token = str(response.get("access_token", "")).strip()
        if not access_token:
            raise WattsAuthError("Watts authentication response did not include access_token")

        expires_in = int(response.get("expires_in", 0) or 0)
        refresh_token = str(response.get("refresh_token", "")).strip()

        self._token = WattsToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.monotonic() + max(1, expires_in),
        )

        self._access_token = self._token.access_token
        self._refresh_token = self._token.refresh_token

        return response

    async def _ensure_access_token(self) -> str:
        """Return a valid access token, reauthenticating when required."""
        if self._token is None:
            await self.async_login()
        elif time.monotonic() >= (self._token.expires_at - 30):
            await self.async_login()

        if self._token is None:
            raise WattsAuthError("No access token available")

        self._access_token = self._token.access_token
        return self._token.access_token

    async def _force_reauthenticate(self) -> None:
        """Drop token cache and authenticate again."""
        self._token = None
        self._access_token = None
        self._refresh_token = None
        await self.async_login()

    async def _async_raw_request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Run a raw HTTP request and return status + decoded payload."""
        timeout = aiohttp.ClientTimeout(total=self._request_timeout)

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                data=data,
                timeout=timeout,
            ) as response:
                status = response.status
                content_type = response.headers.get("Content-Type", "")

                if "json" in content_type:
                    payload: dict[str, Any] = await response.json(content_type=None)
                else:
                    text = await response.text()
                    payload = {"raw": text}

                return status, payload

        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise WattsConnectionError(f"Request to Watts API failed: {err}") from err

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: Mapping[str, str] | None = None,
        allow_api_codes: set[str] | None = None,
        auth_required: bool = True,
        base_url: str = API_BASE_URL,
    ) -> dict[str, Any]:
        """Run a request and validate HTTP + Watts-level success."""
        headers: dict[str, str] = {}
        if auth_required:
            token = await self._ensure_access_token()
            headers["Authorization"] = f"Bearer {token}"

        status, payload = await self._async_raw_request(
            method,
            f"{base_url}{path}",
            headers=headers or None,
            data=data,
        )

        if auth_required and status in (401, 403):
            _LOGGER.debug("Watts API returned HTTP %s for %s, retrying once", status, path)
            await self._force_reauthenticate()
            token = await self._ensure_access_token()
            headers = {"Authorization": f"Bearer {token}"}
            status, payload = await self._async_raw_request(
                method,
                f"{base_url}{path}",
                headers=headers,
                data=data,
            )

        if status in (401, 403):
            raise WattsAuthError(f"Watts API rejected credentials for {path} (HTTP {status})")

        if status >= 400:
            raise WattsApiError(f"Watts API request failed for {path} with HTTP {status}")

        if "code" not in payload:
            return payload

        code_obj = payload.get("code") or {}
        code = str(code_obj.get("code", "")).strip()
        key = str(code_obj.get("key", "")).strip()
        value = str(code_obj.get("value", "")).strip()

        allowed = _SUCCESS_CODES.copy()
        if allow_api_codes:
            allowed.update(allow_api_codes)

        if code and code not in allowed:
            raise WattsApiError(
                f"Watts API error for {path}: code={code}, key={key or 'unknown'}, value={value or 'unknown'}"
            )

        return payload

    async def async_get_user_data(self, *, lang: str | None = None) -> dict[str, Any]:
        """Fetch user/read payload."""
        language = lang or self._default_lang
        payload = {
            "token": REQUEST_TOKEN_LITERAL,
            "email": self._username,
            "lang": language,
        }
        return await self._request("POST", "/api/v0.1/human/user/read/", data=payload)

    async def async_get_smarthome_data(self, smarthome_id: str, *, lang: str | None = None) -> dict[str, Any]:
        """Fetch smarthome/read payload."""
        language = lang or self._default_lang
        payload = {
            "token": REQUEST_TOKEN_LITERAL,
            "smarthome_id": smarthome_id,
            "lang": language,
        }
        return await self._request("POST", "/api/v0.1/human/smarthome/read/", data=payload)

    async def async_get_errors(
        self,
        smarthome_id: str,
        *,
        type_id: str = "0",
        lang: str | None = None,
    ) -> dict[str, Any]:
        """Fetch smarthome/get_errors payload."""
        language = lang or self._default_lang
        payload = {
            "token": REQUEST_TOKEN_LITERAL,
            "smarthome_id": smarthome_id,
            "type_id": type_id,
            "lang": language,
        }
        return await self._request("POST", "/api/v0.1/human/smarthome/get_errors/", data=payload)

    async def async_get_time_offset(self, smarthome_id: str, *, lang: str | None = None) -> dict[str, Any]:
        """Fetch smarthome/time_offset payload."""
        language = lang or self._default_lang
        payload = {
            "smarthome_id": smarthome_id,
            "lang": language,
        }
        return await self._request("POST", "/api/v0.1/human/smarthome/time_offset/", data=payload)

    async def async_check_last_connection(self, smarthome_id: str, *, lang: str | None = None) -> dict[str, Any]:
        """Fetch sandbox/check_last_connexion payload."""
        language = lang or self._default_lang
        payload = {
            "token": REQUEST_TOKEN_LITERAL,
            "smarthome_id": smarthome_id,
            "lang": language,
        }
        return await self._request("POST", "/api/v0.1/human/sandbox/check_last_connexion/", data=payload)

    async def async_check_query_failure(self, smarthome_id: str, *, lang: str | None = None) -> dict[str, Any]:
        """Fetch query/check_failure payload.

        Code=2 (ERR_NO_DATA) is considered non-fatal and returned as-is.
        """
        language = lang or self._default_lang
        payload = {
            "token": REQUEST_TOKEN_LITERAL,
            "smarthome_id": smarthome_id,
            "lang": language,
        }
        return await self._request(
            "POST",
            "/api/v0.1/human/query/check_failure/",
            data=payload,
            allow_api_codes={"2"},
        )

    async def async_push_query(
        self,
        smarthome_id: str,
        query: Mapping[str, str | int | float],
        *,
        lang: str | None = None,
        peremption_ms: str = REQUEST_PEREMPTION_MS,
    ) -> dict[str, Any]:
        """Push a device command through query/push."""
        language = lang or self._default_lang

        payload: dict[str, str] = {
            "token": REQUEST_TOKEN_LITERAL,
            "context": REQUEST_CONTEXT,
            "smarthome_id": smarthome_id,
            "peremption": str(peremption_ms),
            "lang": language,
        }
        for key, value in query.items():
            payload[f"query[{key}]"] = str(value)

        return await self._request("POST", "/api/v0.1/human/query/push/", data=payload)
