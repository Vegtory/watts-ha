"""API client for Watts SmartHome."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

import aiohttp

from .const import (
    API_BASE_URL,
    AUTH_BASE_URL,
    AUTH_TOKEN_ENDPOINT,
    DEFAULT_CONTEXT,
    DEFAULT_LANG,
    DEFAULT_PEREMPTION_MS,
    ENDPOINT_QUERY_PUSH,
    ENDPOINT_SMARTHOME_READ,
    ENDPOINT_USER_READ,
)

_LOGGER = logging.getLogger(__name__)

_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30)
_TOKEN_EXPIRY_MARGIN = timedelta(seconds=30)
_SUCCESS_CODES = {"1", "8"}
_ENDPOINT_SMARTHOME_GET_ERRORS = "/api/v0.1/human/smarthome/get_errors/"
_ENDPOINT_CHECK_LAST_CONNECTION = "/api/v0.1/human/sandbox/check_last_connexion/"
_ENDPOINT_TIME_OFFSET = "/api/v0.1/human/smarthome/time_offset/"
_ENDPOINT_CONVERT_PROGRAM = "/api/v0.1/human/sandbox/convert_program/"
_ENDPOINT_QUERY_CHECK_FAILURE = "/api/v0.1/human/query/check_failure/"


class WattsApiError(Exception):
    """Base error from the Watts API client."""


class WattsAuthError(WattsApiError):
    """Authentication error from the Watts API client."""


class WattsConnectionError(WattsApiError):
    """Connectivity error from the Watts API client."""


class WattsApiClient:
    """Async client for the Watts SmartHome cloud API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        *,
        lang: str = DEFAULT_LANG,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._lang = lang

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: datetime | None = None

        self._token_lock = asyncio.Lock()

    @property
    def lang(self) -> str:
        """Return active API language."""
        return self._lang

    def set_lang(self, lang: str) -> None:
        """Set active API language."""
        if lang:
            self._lang = lang

    async def async_login(self) -> dict[str, Any]:
        """Login via OAuth2 password grant and store token data."""
        async with self._token_lock:
            return await self._async_login_locked()

    async def _async_login_locked(self) -> dict[str, Any]:
        payload = {
            "grant_type": "password",
            "username": self._username,
            "password": self._password,
            "client_id": "app-front",
        }
        status, data = await self._async_raw_request(
            "POST",
            f"{AUTH_BASE_URL}{AUTH_TOKEN_ENDPOINT}",
            data=payload,
        )
        if status in (401, 403):
            raise WattsAuthError("Invalid username or password")
        if status >= 400:
            raise WattsApiError(f"Login failed with HTTP status {status}")

        self._store_tokens(data)
        _LOGGER.debug("Watts login successful for %s", self._username)
        return data

    async def _async_refresh_token_locked(self) -> None:
        if not self._refresh_token:
            raise WattsAuthError("No refresh token available")

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": "app-front",
        }
        status, data = await self._async_raw_request(
            "POST",
            f"{AUTH_BASE_URL}{AUTH_TOKEN_ENDPOINT}",
            data=payload,
        )
        if status in (401, 403):
            raise WattsAuthError("Refresh token rejected")
        if status >= 400:
            raise WattsApiError(f"Token refresh failed with HTTP status {status}")

        self._store_tokens(data)
        _LOGGER.debug("Watts token refresh successful for %s", self._username)

    def _store_tokens(self, payload: Mapping[str, Any]) -> None:
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise WattsAuthError("Token response missing access_token")

        self._access_token = access_token
        refresh_token = payload.get("refresh_token")
        self._refresh_token = refresh_token if isinstance(refresh_token, str) else None

        expires_in = payload.get("expires_in", 300)
        try:
            expires_seconds = int(expires_in)
        except (TypeError, ValueError):
            expires_seconds = 300
        self._token_expires_at = datetime.now(tz=UTC) + timedelta(seconds=expires_seconds)

    async def _ensure_access_token(self) -> None:
        async with self._token_lock:
            now = datetime.now(tz=UTC)
            if self._access_token is None:
                await self._async_login_locked()
                return

            if self._token_expires_at and now < (self._token_expires_at - _TOKEN_EXPIRY_MARGIN):
                return

            try:
                await self._async_refresh_token_locked()
            except WattsApiError:
                await self._async_login_locked()

    async def _force_reauthenticate(self) -> None:
        async with self._token_lock:
            try:
                if self._refresh_token:
                    await self._async_refresh_token_locked()
                    return
            except WattsApiError:
                pass
            await self._async_login_locked()

    async def _async_raw_request(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            async with self._session.request(
                method,
                url,
                data=data,
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            ) as response:
                text = await response.text()
                payload: dict[str, Any]
                if text:
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        payload = {"raw": text}
                else:
                    payload = {}
                return response.status, payload
        except (aiohttp.ClientError, TimeoutError) as err:
            raise WattsConnectionError(f"Request to Watts API failed: {err}") from err

    async def _async_api_post(
        self,
        endpoint: str,
        payload: Mapping[str, Any] | None = None,
        *,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        await self._ensure_access_token()
        if self._access_token is None:
            raise WattsAuthError("No access token available")

        request_payload: dict[str, Any] = dict(payload or {})
        request_payload.setdefault("lang", self._lang)
        request_payload.setdefault("token", self._access_token)

        status, data = await self._async_raw_request(
            "POST",
            f"{API_BASE_URL}{endpoint}",
            data=request_payload,
            headers={"Authorization": f"Bearer {self._access_token}"},
        )

        if status in (401, 403):
            if retry_auth:
                await self._force_reauthenticate()
                return await self._async_api_post(endpoint, payload, retry_auth=False)
            raise WattsAuthError("Authentication rejected by Watts API")
        if status >= 400:
            raise WattsApiError(f"Watts API returned HTTP {status} for {endpoint}")

        self._raise_for_api_code(data, endpoint)
        return data

    def _raise_for_api_code(self, payload: Mapping[str, Any], endpoint: str) -> None:
        code_block = payload.get("code")
        if not isinstance(code_block, Mapping):
            return

        code = str(code_block.get("code", ""))
        if not code or code in _SUCCESS_CODES:
            return

        key = str(code_block.get("key", "UNKNOWN"))
        value = str(code_block.get("value", ""))
        message = f"Watts API error for {endpoint}: code={code}, key={key}, value={value}"
        if "AUTH" in key.upper():
            raise WattsAuthError(message)
        raise WattsApiError(message)

    async def async_get_user_data(self) -> dict[str, Any]:
        """Fetch user profile and smarthome list."""
        return await self._async_api_post(
            ENDPOINT_USER_READ,
            {
                "email": self._username,
            },
        )

    async def async_get_smarthome_data(self, smarthome_id: str) -> dict[str, Any]:
        """Fetch full state for a smarthome."""
        return await self._async_api_post(
            ENDPOINT_SMARTHOME_READ,
            {
                "smarthome_id": smarthome_id,
            },
        )

    async def async_push_query(
        self,
        smarthome_id: str,
        query_values: Mapping[str, Any],
        *,
        context: str = DEFAULT_CONTEXT,
        peremption_ms: int = DEFAULT_PEREMPTION_MS,
    ) -> dict[str, Any]:
        """Push a query command to a device."""
        if "id_device" not in query_values:
            raise WattsApiError("query_values must include id_device")

        payload: dict[str, Any] = {
            "smarthome_id": smarthome_id,
            "context": str(context),
            "peremption": str(peremption_ms),
        }
        for field, value in query_values.items():
            payload[f"query[{field}]"] = str(value)

        try:
            return await self._async_api_post(ENDPOINT_QUERY_PUSH, payload)
        except WattsApiError:
            # Some environments expect token="true" in form payload while auth stays in header.
            payload_with_bool_token = dict(payload)
            payload_with_bool_token["token"] = "true"
            return await self._async_api_post(ENDPOINT_QUERY_PUSH, payload_with_bool_token)

    async def async_get_errors(self, smarthome_id: str, *, type_id: str = "all") -> dict[str, Any]:
        """Fetch errors for a smarthome."""
        return await self._async_api_post(
            _ENDPOINT_SMARTHOME_GET_ERRORS,
            {"smarthome_id": smarthome_id, "type_id": type_id},
        )

    async def async_check_last_connection(self, smarthome_id: str) -> dict[str, Any]:
        """Fetch last connection info for a smarthome."""
        return await self._async_api_post(
            _ENDPOINT_CHECK_LAST_CONNECTION,
            {"smarthome_id": smarthome_id},
        )

    async def async_get_time_offset(self, smarthome_id: str) -> dict[str, Any]:
        """Fetch time offset info for a smarthome."""
        return await self._async_api_post(
            _ENDPOINT_TIME_OFFSET,
            {"smarthome_id": smarthome_id},
        )

    async def async_convert_program(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Convert program payload into UI-friendly data."""
        return await self._async_api_post(_ENDPOINT_CONVERT_PROGRAM, payload)

    async def async_check_query_failure(self, smarthome_id: str) -> dict[str, Any]:
        """Check whether backend reported query execution failures."""
        return await self._async_api_post(
            _ENDPOINT_QUERY_CHECK_FAILURE,
            {"smarthome_id": smarthome_id},
        )

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Backwards-compatible low-level request wrapper."""
        request_method = method.upper()
        if request_method == "POST":
            return await self._async_api_post(endpoint, data)

        if request_method == "GET":
            await self._ensure_access_token()
            if self._access_token is None:
                raise WattsAuthError("No access token available")

            status, payload = await self._async_raw_request(
                "GET",
                f"{API_BASE_URL}{endpoint}",
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            if status in (401, 403):
                await self._force_reauthenticate()
                if self._access_token is None:
                    raise WattsAuthError("No access token available")
                status, payload = await self._async_raw_request(
                    "GET",
                    f"{API_BASE_URL}{endpoint}",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                )
            if status >= 400:
                raise WattsApiError(f"Watts API returned HTTP {status} for {endpoint}")
            return payload

        raise WattsApiError(f"Unsupported method for _request: {method}")
