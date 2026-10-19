"""Shared fixtures for Watts SmartHome tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watts_smarthome import coordinator as coordinator_module
from custom_components.watts_smarthome.api import WattsConnectionStatus, WattsFailureCheck
from custom_components.watts_smarthome.const import DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
SMARTHOME_ID = "SH_TEST_1"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components in every test."""
    yield


@pytest.fixture(autouse=True)
def no_real_session():
    """Never open a real HTTP session in tests."""
    with (
        patch("custom_components.watts_smarthome.async_get_clientsession", return_value=MagicMock()),
        patch("custom_components.watts_smarthome.config_flow.async_get_clientsession", return_value=MagicMock()),
    ):
        yield


@pytest.fixture(autouse=True)
def fast_sync(monkeypatch):
    """Shrink the sync timings so tests run in milliseconds."""
    monkeypatch.setattr(coordinator_module, "WRITE_DEBOUNCE_SECONDS", 0.01)
    monkeypatch.setattr(coordinator_module, "POST_WRITE_QUIET_SECONDS", 0.05)
    monkeypatch.setattr(coordinator_module, "CHECK_FAILURE_MARGIN_SECONDS", 0.01)
    monkeypatch.setattr(coordinator_module, "CONFIRM_RETRY_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(coordinator_module, "CONFIRM_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(coordinator_module, "PEREMPTION_STEPS_MS", (60, 80, 100, 120))


class FakeWattsClient:
    """In-memory stand-in for WattsApiClient that behaves like the cloud."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.user = load_fixture("user_read")
        self.read = load_fixture("smarthome_read")
        self.errors = load_fixture("get_errors")
        self.seconds_since_contact: int | None = 5
        self.fail_next_command = False
        self.apply_pushes = True
        self.pushes: list[dict[str, Any]] = []
        self.calls: list[str] = []
        self.login_error: Exception | None = None
        self.read_error: Exception | None = None

    async def async_login(self) -> dict[str, Any]:
        self.calls.append("login")
        if self.login_error:
            raise self.login_error
        return {"access_token": "x"}

    async def async_get_user_data(self, *, lang: str | None = None) -> dict[str, Any]:
        self.calls.append("user_read")
        if self.login_error:
            raise self.login_error
        return copy.deepcopy(self.user)

    async def async_get_smarthome_data(self, smarthome_id: str, *, lang: str | None = None) -> dict[str, Any]:
        self.calls.append("smarthome_read")
        if self.read_error:
            raise self.read_error
        return copy.deepcopy(self.read)

    async def async_get_errors(self, smarthome_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("get_errors")
        return copy.deepcopy(self.errors)

    async def async_check_last_connection(self, smarthome_id: str, **kwargs: Any) -> WattsConnectionStatus:
        self.calls.append("check_last_connexion")
        return WattsConnectionStatus(seconds_since_contact=self.seconds_since_contact)

    async def async_check_query_failure(self, smarthome_id: str, **kwargs: Any) -> WattsFailureCheck:
        self.calls.append("check_failure")
        if self.fail_next_command:
            self.fail_next_command = False
            return WattsFailureCheck(failed=True, details={"reason": "expired"})
        return WattsFailureCheck(failed=False, details={})

    async def async_push_query(self, smarthome_id: str, query: dict[str, str], **kwargs: Any) -> dict[str, Any]:
        self.calls.append("push")
        self.pushes.append({"query": dict(query), **kwargs})
        if self.apply_pushes and not self.fail_next_command:
            self.apply(query)
        return {"code": {"code": "8", "key": "OK_SET"}}

    def apply(self, query: dict[str, str]) -> None:
        """Make the next read return the pushed values (what the cloud does)."""
        data = self.read["data"]
        for device in [*data["devices"], *(d for zone in data["zones"] for d in zone["devices"])]:
            if device["id_device"] == query["id_device"]:
                for key, value in query.items():
                    if key not in ("id_device", "time_boost"):
                        device[key] = value


@pytest.fixture
def fake_client() -> FakeWattsClient:
    return FakeWattsClient()


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        unique_id="42",
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"},
    )


@pytest.fixture
async def setup_integration(hass, mock_entry, fake_client):
    """Set up the integration with the fake client."""
    mock_entry.add_to_hass(hass)
    with patch("custom_components.watts_smarthome.WattsApiClient", return_value=fake_client):
        assert await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    return mock_entry
