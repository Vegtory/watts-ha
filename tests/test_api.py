"""Tests for the HTTP client (payloads and response parsing taken from the browser capture)."""

from __future__ import annotations

import time

import pytest

from custom_components.watts_smarthome.api import WattsApiClient, WattsApiError, WattsAuthError, WattsConnectionError
from custom_components.watts_smarthome.const import API_BASE_URL, AUTH_BASE_URL, TOKEN_PATH

TOKEN_URL = f"{AUTH_BASE_URL}{TOKEN_PATH}"
TOKEN_RESPONSE = {
    "access_token": "access-1",
    "refresh_token": "refresh-1",
    "expires_in": 300,
    "refresh_expires_in": 3000,
}
NO_DATA = {"code": {"code": "2", "key": "ERR_NO_DATA", "value": "No data"}, "data": {}}


@pytest.fixture
async def client(hass, aioclient_mock):
    session = aioclient_mock.create_session(hass.loop)
    yield WattsApiClient(session=session, username="user@example.com", password="secret")
    await session.close()


def _form(call) -> dict:
    return dict(call[2])


async def test_login_then_refresh_token(client, aioclient_mock) -> None:
    aioclient_mock.post(TOKEN_URL, json=TOKEN_RESPONSE)
    aioclient_mock.post(f"{API_BASE_URL}/api/v0.1/human/user/read/", json={"code": {"code": "1"}, "data": {}})

    await client.async_get_user_data()
    assert _form(aioclient_mock.mock_calls[0])["grant_type"] == "password"
    assert aioclient_mock.mock_calls[1][3]["Authorization"] == "Bearer access-1"

    # Expire the access token: the client must use the refresh token, not the password.
    client._token.expires_at = time.monotonic()
    await client.async_get_user_data()
    refresh = _form(aioclient_mock.mock_calls[2])
    assert refresh == {"grant_type": "refresh_token", "refresh_token": "refresh-1", "client_id": "app-front"}


async def test_rejected_refresh_falls_back_to_password(client, aioclient_mock) -> None:
    aioclient_mock.post(TOKEN_URL, json=TOKEN_RESPONSE)
    await client.async_login()
    client._token.expires_at = time.monotonic()

    aioclient_mock.clear_requests()
    aioclient_mock.post(TOKEN_URL, status=400)
    with pytest.raises(WattsAuthError):
        await client._ensure_access_token()
    grants = [_form(call)["grant_type"] for call in aioclient_mock.mock_calls]
    assert grants == ["refresh_token", "password"]


async def test_401_triggers_one_relogin(client, aioclient_mock) -> None:
    aioclient_mock.post(TOKEN_URL, json=TOKEN_RESPONSE)
    aioclient_mock.post(f"{API_BASE_URL}/api/v0.1/human/smarthome/read/", status=401)
    with pytest.raises(WattsAuthError):
        await client.async_get_smarthome_data("SH")
    reads = [c for c in aioclient_mock.mock_calls if "smarthome/read" in str(c[1])]
    assert len(reads) == 2


async def test_api_error_code_raises(client, aioclient_mock) -> None:
    aioclient_mock.post(TOKEN_URL, json=TOKEN_RESPONSE)
    aioclient_mock.post(
        f"{API_BASE_URL}/api/v0.1/human/smarthome/read/",
        json={"code": {"code": "5", "key": "ERR_X", "value": "Broken"}},
    )
    with pytest.raises(WattsApiError, match="ERR_X"):
        await client.async_get_smarthome_data("SH")


async def test_connection_error(client, aioclient_mock) -> None:
    aioclient_mock.post(TOKEN_URL, exc=TimeoutError())
    with pytest.raises(WattsConnectionError):
        await client.async_login()


async def test_check_last_connection(client, aioclient_mock) -> None:
    aioclient_mock.post(TOKEN_URL, json=TOKEN_RESPONSE)
    aioclient_mock.post(
        f"{API_BASE_URL}/api/v0.1/human/sandbox/check_last_connexion/",
        json={"code": {"code": "1", "key": "OK"}, "data": {"diff": 6, "diffObj": {"seconds": 6}}},
    )
    status = await client.async_check_last_connection("SH")
    assert status.seconds_since_contact == 6


async def test_check_last_connection_never(client, aioclient_mock) -> None:
    aioclient_mock.post(TOKEN_URL, json=TOKEN_RESPONSE)
    aioclient_mock.post(f"{API_BASE_URL}/api/v0.1/human/sandbox/check_last_connexion/", json=NO_DATA)
    status = await client.async_check_last_connection("SH")
    assert status.seconds_since_contact is None


async def test_check_failure_no_data_means_delivered(client, aioclient_mock) -> None:
    aioclient_mock.post(TOKEN_URL, json=TOKEN_RESPONSE)
    aioclient_mock.post(f"{API_BASE_URL}/api/v0.1/human/query/check_failure/", json=NO_DATA)
    result = await client.async_check_query_failure("SH")
    assert result.failed is False


async def test_check_failure_ok_means_failed(client, aioclient_mock) -> None:
    aioclient_mock.post(TOKEN_URL, json=TOKEN_RESPONSE)
    aioclient_mock.post(
        f"{API_BASE_URL}/api/v0.1/human/query/check_failure/",
        json={"code": {"code": "1", "key": "OK", "value": "OK"}, "data": {"C001-000": "expired"}},
    )
    result = await client.async_check_query_failure("SH")
    assert result.failed is True
    assert result.details == {"C001-000": "expired"}


async def test_push_payload_matches_app(client, aioclient_mock) -> None:
    aioclient_mock.post(TOKEN_URL, json=TOKEN_RESPONSE)
    aioclient_mock.post(
        f"{API_BASE_URL}/api/v0.1/human/query/push/",
        json={"code": {"code": "8", "key": "OK_SET", "value": "Insert / update success"}, "data": {}},
    )
    await client.async_push_query("SH", {"id_device": "C001-000", "gv_mode": "3", "nv_mode": "3"}, peremption_ms=20000)
    form = _form(aioclient_mock.mock_calls[-1])
    assert form == {
        "token": "true",
        "context": "1",
        "smarthome_id": "SH",
        "peremption": "20000",
        "lang": "en_GB",
        "query[id_device]": "C001-000",
        "query[gv_mode]": "3",
        "query[nv_mode]": "3",
    }
