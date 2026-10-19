"""Async API client for the Watts SmartHome cloud endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    AUTH_BASE_URL,
    DEFAULT_LANG,
    PEREMPTION_STEPS_MS,
    REQUEST_CONTEXT,
    REQUEST_TOKEN_LITERAL,
    TOKEN_CLIENT_ID,
    TOKEN_PATH,
)

_LOGGER = logging.getLogger(__name__)

# code 1 = OK (reads), code 8 = OK_SET (writes)
_SUCCESS_CODES = {"1", "8"}
_CODE_NO_DATA = "2"
# Renew the access token this many seconds before it expires.
_TOKEN_EXPIRY_MARGIN = 30


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
    refresh_expires_at: float


@dataclass(frozen=True, slots=True)
class WattsConnectionStatus:
    """Result of sandbox/check_last_connexion."""

    seconds_since_contact: int | None
    """Seconds since the central unit last talked to the cloud; None if never."""


@dataclass(frozen=True, slots=True)
class WattsFailureCheck:
    """Result of query/check_failure."""

    failed: bool
    """True when the cloud reports an expired, undelivered command."""
    details: dict[str, Any]


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
        self._token_lock = asyncio.Lock()

    @property
    def username(self) -> str:
        """Return the account e-mail."""
        return self._username

    # --- Authentication ---------------------------------------------------------

    async def async_login(self) -> dict[str, Any]:
        """Authenticate with username/password and cache the token."""
        return await self._async_token_request(
            {
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
                "client_id": TOKEN_CLIENT_ID,
            }
        )

    async def _async_refresh(self, refresh_token: str) -> dict[str, Any]:
        """Swap a refresh token for a new access token (what the web app does)."""
        return await self._async_token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": TOKEN_CLIENT_ID,
            }
        )

    async def _async_token_request(self, payload: dict[str, str]) -> dict[str, Any]:
        status, response = await self._async_raw_request(
            "POST",
            f"{AUTH_BASE_URL}{TOKEN_PATH}",
            data=payload,
        )
        if status in (400, 401, 403):
            raise WattsAuthError(f"Watts authentication failed with HTTP {status}")
        if status >= 400:
            raise WattsApiError(f"Watts authentication endpoint returned HTTP {status}")

        access_token = str(response.get("access_token", "")).strip()
        if not access_token:
            raise WattsAuthError("Watts authentication response did not include access_token")

        now = time.monotonic()
        expires_in = int(response.get("expires_in", 0) or 0)
        refresh_expires_in = int(response.get("refresh_expires_in", 0) or 0)
        self._token = WattsToken(
            access_token=access_token,
            refresh_token=str(response.get("refresh_token", "")).strip(),
            expires_at=now + max(1, expires_in),
            refresh_expires_at=now + max(0, refresh_expires_in),
        )
        return response

    async def _ensure_access_token(self) -> str:
        """Return a valid access token, refreshing or logging in when needed."""
        async with self._token_lock:
            now = time.monotonic()
            token = self._token
            if token is not None and now < token.expires_at - _TOKEN_EXPIRY_MARGIN:
                return token.access_token

            if token is not None and token.refresh_token and now < token.refresh_expires_at - _TOKEN_EXPIRY_MARGIN:
                try:
                    await self._async_refresh(token.refresh_token)
                except WattsAuthError:
                    _LOGGER.debug("Watts refresh token rejected, logging in again")
                    await self.async_login()
            else:
                await self.async_login()

            assert self._token is not None
            return self._token.access_token

    async def _force_reauthenticate(self) -> None:
        """Drop token cache and authenticate again with the password."""
        async with self._token_lock:
            self._token = None
            await self.async_login()

    # --- Transport ----------------------------------------------------------------

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
                text = await response.text()
        except (TimeoutError, aiohttp.ClientError) as err:
            raise WattsConnectionError(f"Request to Watts API failed: {err}") from err

        # Parse by content, not Content-Type: error pages are HTML, data is JSON.
        try:
            decoded = json.loads(text) if text else {}
        except ValueError:
            return status, {"raw": text}
        return status, decoded if isinstance(decoded, dict) else {"raw": decoded}

    async def _request(
        self,
        path: str,
        *,
        data: Mapping[str, str] | None = None,
        allow_api_codes: set[str] | None = None,
    ) -> dict[str, Any]:
        """POST to the API and validate HTTP + Watts-level success."""
        url = f"{API_BASE_URL}{path}"
        token = await self._ensure_access_token()
        status, payload = await self._async_raw_request(
            "POST", url, headers={"Authorization": f"Bearer {token}"}, data=data
        )

        if status in (401, 403):
            _LOGGER.debug("Watts API returned HTTP %s for %s, retrying once", status, path)
            await self._force_reauthenticate()
            token = await self._ensure_access_token()
            status, payload = await self._async_raw_request(
                "POST", url, headers={"Authorization": f"Bearer {token}"}, data=data
            )

        if status in (401, 403):
            raise WattsAuthError(f"Watts API rejected credentials for {path} (HTTP {status})")
        if status >= 400:
            raise WattsApiError(f"Watts API request failed for {path} with HTTP {status}")

        code_obj = payload.get("code")
        if not isinstance(code_obj, dict):
            return payload

        code = str(code_obj.get("code", "")).strip()
        allowed = _SUCCESS_CODES | (allow_api_codes or set())
        if code and code not in allowed:
            key = str(code_obj.get("key", "")).strip() or "unknown"
            value = str(code_obj.get("value", "")).strip() or "unknown"
            raise WattsApiError(f"Watts API error for {path}: code={code}, key={key}, value={value}")

        return payload

    def _lang(self, lang: str | None) -> str:
        return lang or self._default_lang

    # --- Reads --------------------------------------------------------------------

    async def async_get_user_data(self, *, lang: str | None = None) -> dict[str, Any]:
        """Fetch user/read payload (profile + smarthome list)."""
        return await self._request(
            "/api/v0.1/human/user/read/",
            data={"token": REQUEST_TOKEN_LITERAL, "email": self._username, "lang": self._lang(lang)},
        )

    async def async_get_smarthome_data(self, smarthome_id: str, *, lang: str | None = None) -> dict[str, Any]:
        """Fetch smarthome/read payload (zones + devices)."""
        return await self._request(
            "/api/v0.1/human/smarthome/read/",
            data={"token": REQUEST_TOKEN_LITERAL, "smarthome_id": smarthome_id, "lang": self._lang(lang)},
        )

    async def async_get_errors(
        self,
        smarthome_id: str,
        *,
        type_id: str = "0",
        lang: str | None = None,
    ) -> dict[str, Any]:
        """Fetch smarthome/get_errors payload."""
        return await self._request(
            "/api/v0.1/human/smarthome/get_errors/",
            data={
                "token": REQUEST_TOKEN_LITERAL,
                "smarthome_id": smarthome_id,
                "type_id": type_id,
                "lang": self._lang(lang),
            },
        )

    async def async_check_last_connection(self, smarthome_id: str, *, lang: str | None = None) -> WattsConnectionStatus:
        """Return how long ago the central unit last contacted the cloud."""
        payload = await self._request(
            "/api/v0.1/human/sandbox/check_last_connexion/",
            data={"token": REQUEST_TOKEN_LITERAL, "smarthome_id": smarthome_id, "lang": self._lang(lang)},
            allow_api_codes={_CODE_NO_DATA},
        )
        data = payload.get("data")
        diff = data.get("diff") if isinstance(data, dict) else None
        try:
            seconds = int(diff) if diff is not None else None
        except (TypeError, ValueError):
            seconds = None
        return WattsConnectionStatus(seconds_since_contact=seconds)

    async def async_check_query_failure(self, smarthome_id: str, *, lang: str | None = None) -> WattsFailureCheck:
        """Ask whether a recently pushed command expired undelivered.

        The web app treats `OK` as "a failure was recorded" and `ERR_NO_DATA`
        (code 2) as "nothing failed".
        """
        payload = await self._request(
            "/api/v0.1/human/query/check_failure/",
            data={"token": REQUEST_TOKEN_LITERAL, "smarthome_id": smarthome_id, "lang": self._lang(lang)},
            allow_api_codes={_CODE_NO_DATA},
        )
        code_obj = payload.get("code") if isinstance(payload.get("code"), dict) else {}
        key = str(code_obj.get("key", "")).strip()
        data = payload.get("data")
        return WattsFailureCheck(failed=key == "OK", details=data if isinstance(data, dict) else {})

    # --- Writes -------------------------------------------------------------------

    async def async_push_query(
        self,
        smarthome_id: str,
        query: Mapping[str, str | int | float],
        *,
        lang: str | None = None,
        peremption_ms: int = PEREMPTION_STEPS_MS[0],
        context: str = REQUEST_CONTEXT,
    ) -> dict[str, Any]:
        """Queue a device command; the central unit picks it up within `peremption_ms`."""
        payload: dict[str, str] = {
            "token": REQUEST_TOKEN_LITERAL,
            "context": context,
            "smarthome_id": smarthome_id,
            "peremption": str(peremption_ms),
            "lang": self._lang(lang),
        }
        for key, value in query.items():
            payload[f"query[{key}]"] = str(value)

        return await self._request("/api/v0.1/human/query/push/", data=payload)
