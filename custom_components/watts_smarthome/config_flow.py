"""Config flow for Watts SmartHome."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WattsApiClient, WattsApiError, WattsAuthError, WattsConnectionError
from .const import (
    CONF_LANG,
    CONF_SCAN_INTERVAL,
    DEFAULT_LANG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


def _options_schema(
    current_options: dict[str, Any],
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current_options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            vol.Required(
                CONF_LANG,
                default=current_options.get(CONF_LANG, DEFAULT_LANG),
            ): str,
        }
    )


async def _async_validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    api = WattsApiClient(
        session=async_get_clientsession(hass),
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        lang=DEFAULT_LANG,
    )
    user_payload = await api.async_get_user_data()
    smarthomes = user_payload.get("data", {}).get("smarthomes", [])
    if smarthomes:
        first_smarthome = smarthomes[0]
        if isinstance(first_smarthome, dict):
            title = first_smarthome.get("label")
            if isinstance(title, str) and title.strip():
                return {"title": title.strip()}
    return {"title": data[CONF_USERNAME]}


class WattsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Watts SmartHome."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            try:
                info = await _async_validate_input(self.hass, user_input)
            except WattsAuthError:
                errors["base"] = "invalid_auth"
            except (WattsConnectionError, WattsApiError):
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - defensive
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return WattsOptionsFlow(entry)


class WattsOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Watts SmartHome."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self._entry.options),
        )
