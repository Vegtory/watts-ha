"""Config flow for Watts SmartHome."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WattsApiClient, WattsApiError, WattsAuthError, WattsConnectionError
from .const import (
    CONF_ENTRY_TITLE_FALLBACK,
    CONF_LANG,
    CONF_SCAN_INTERVAL,
    DEFAULT_LANG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .models import parse_user_profile


class WattsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Watts SmartHome."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return options flow handler."""
        return WattsOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Handle initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            lang = user_input[CONF_LANG].strip() or DEFAULT_LANG
            scan_interval = max(int(user_input[CONF_SCAN_INTERVAL]), MIN_SCAN_INTERVAL)

            try:
                profile = await self._async_validate_credentials(
                    username=username,
                    password=password,
                    lang=lang,
                )
            except WattsAuthError:
                errors["base"] = "invalid_auth"
            except WattsConnectionError:
                errors["base"] = "cannot_connect"
            except WattsApiError:
                errors["base"] = "unknown"
            except Exception:
                errors["base"] = "unknown"
            else:
                unique_id = profile.user_id or username.lower()
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                title = profile.email or username or CONF_ENTRY_TITLE_FALLBACK
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_LANG: lang,
                        CONF_SCAN_INTERVAL: scan_interval,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_LANG, default=DEFAULT_LANG): str,
                    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                        int,
                        vol.Range(min=MIN_SCAN_INTERVAL),
                    ),
                }
            ),
            errors=errors,
        )

    async def _async_validate_credentials(
        self,
        *,
        username: str,
        password: str,
        lang: str,
    ):
        """Validate credentials by logging in and loading user data."""
        session = async_get_clientsession(self.hass)
        client = WattsApiClient(
            session=session,
            username=username,
            password=password,
            default_lang=lang,
        )
        await client.async_login()
        payload = await client.async_get_user_data(lang=lang)
        return parse_user_profile(payload)


class WattsOptionsFlow(config_entries.OptionsFlow):
    """Handle Watts integration options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_LANG: user_input[CONF_LANG].strip() or DEFAULT_LANG,
                    CONF_SCAN_INTERVAL: max(int(user_input[CONF_SCAN_INTERVAL]), MIN_SCAN_INTERVAL),
                },
            )

        lang = self._config_entry.options.get(
            CONF_LANG,
            self._config_entry.data.get(CONF_LANG, DEFAULT_LANG),
        )
        scan_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LANG, default=lang): str,
                    vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                        int,
                        vol.Range(min=MIN_SCAN_INTERVAL),
                    ),
                }
            ),
        )
