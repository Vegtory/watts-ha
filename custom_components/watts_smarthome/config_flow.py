"""Config flow for Watts SmartHome integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .api import WattsApiClient, WattsApiError, WattsAuthError
from .const import (
    CONF_POLLING_INTERVAL,
    DEFAULT_POLLING_INTERVAL,
    DOMAIN,
    MAX_POLLING_INTERVAL,
    MIN_POLLING_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    session = aiohttp_client.async_get_clientsession(hass)
    client = WattsApiClient(
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        session=session,
    )

    try:
        # Test authentication
        await client.async_login()
        
        # Try to fetch user data to ensure API is accessible
        user_data = await client.async_get_user_data()
        
        if "data" not in user_data:
            raise WattsApiError("Invalid response from API")

        email = user_data.get("data", {}).get("email", data[CONF_USERNAME])
        
        return {"title": email}

    finally:
        # Don't close the session as we don't own it
        pass


class WattsSmartHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Watts SmartHome."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except WattsAuthError:
                errors["base"] = "invalid_auth"
            except WattsApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create unique ID based on username to prevent duplicates
                await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WattsSmartHomeOptionsFlow:
        """Get the options flow for this handler."""
        return WattsSmartHomeOptionsFlow(config_entry)


class WattsSmartHomeOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Watts SmartHome."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLLING_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_POLLING_INTERVAL, max=MAX_POLLING_INTERVAL),
                    ),
                }
            ),
        )
