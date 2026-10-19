"""Config flow for Watts SmartHome."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType
import voluptuous as vol

from .api import WattsApiClient, WattsAuthError, WattsConnectionError, WattsError
from .const import (
    CONF_ENTRY_TITLE_FALLBACK,
    CONF_LANG,
    CONF_SCAN_INTERVAL,
    DEFAULT_LANG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .models import WattsUserProfile, parse_user_profile

_LOGGER = logging.getLogger(__name__)

_EMAIL_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username"))
_PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password"))


async def _async_validate(hass, username: str, password: str, lang: str) -> WattsUserProfile:
    """Log in and load the profile; raises WattsError subclasses."""
    client = WattsApiClient(
        session=async_get_clientsession(hass),
        username=username,
        password=password,
        default_lang=lang,
    )
    await client.async_login()
    return parse_user_profile(await client.async_get_user_data(lang=lang))


def _error_key(err: Exception) -> str:
    if isinstance(err, WattsAuthError):
        return "invalid_auth"
    if isinstance(err, WattsConnectionError):
        return "cannot_connect"
    return "unknown"


class WattsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Watts SmartHome."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return options flow handler."""
        return WattsOptionsFlow()

    async def _async_try_login(
        self, username: str, password: str, lang: str, errors: dict[str, str]
    ) -> WattsUserProfile | None:
        try:
            return await _async_validate(self.hass, username, password, lang)
        except WattsError as err:
            errors["base"] = _error_key(err)
        except Exception:
            _LOGGER.exception("Unexpected error while validating Watts credentials")
            errors["base"] = "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            profile = await self._async_try_login(username, password, DEFAULT_LANG, errors)
            if profile is not None:
                await self.async_set_unique_id(profile.user_id or username.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=profile.email or username or CONF_ENTRY_TITLE_FALLBACK,
                    data={CONF_USERNAME: username, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {vol.Required(CONF_USERNAME): _EMAIL_SELECTOR, vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR}
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication when the stored password stops working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for a new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        username = entry.data[CONF_USERNAME]

        if user_input is not None:
            profile = await self._async_try_login(username, user_input[CONF_PASSWORD], DEFAULT_LANG, errors)
            if profile is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR}),
            description_placeholders={"username": username},
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the account e-mail or password."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            profile = await self._async_try_login(username, user_input[CONF_PASSWORD], DEFAULT_LANG, errors)
            if profile is not None:
                await self.async_set_unique_id(profile.user_id or username.lower())
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_USERNAME: username, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {vol.Required(CONF_USERNAME): _EMAIL_SELECTOR, vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR}
                ),
                {CONF_USERNAME: entry.data[CONF_USERNAME]},
            ),
            errors=errors,
        )


class WattsOptionsFlow(OptionsFlow):
    """Handle Watts integration options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_LANG: user_input[CONF_LANG].strip() or DEFAULT_LANG,
                    CONF_SCAN_INTERVAL: max(int(user_input[CONF_SCAN_INTERVAL]), MIN_SCAN_INTERVAL),
                },
            )

        entry = self.config_entry
        lang = entry.options.get(CONF_LANG, entry.data.get(CONF_LANG, DEFAULT_LANG))
        scan_interval = max(
            MIN_SCAN_INTERVAL,
            int(entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LANG, default=lang): str,
                    vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=3600)
                    ),
                }
            ),
        )
