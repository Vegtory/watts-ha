"""The Watts SmartHome integration."""
from __future__ import annotations

from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, config_validation as cv

from .api import WattsApiClient, WattsApiError
from .const import (
    CONF_POLLING_INTERVAL,
    DATA_API_CLIENT,
    DATA_COORDINATOR,
    DEFAULT_LANG,
    DEFAULT_POLLING_INTERVAL,
    DOMAIN,
    SERVICE_APPLY_PROGRAM,
    SERVICE_CONVERT_PROGRAM,
    SERVICE_UPDATE_NOW,
)
from .coordinator import WattsCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER]

# Service schemas
SERVICE_APPLY_PROGRAM_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("program_data"): dict,
        vol.Optional("lang", default=DEFAULT_LANG): cv.string,
    }
)

SERVICE_CONVERT_PROGRAM_SCHEMA = vol.Schema(
    {
        vol.Required("program_data"): dict,
        vol.Optional("lang", default=DEFAULT_LANG): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Watts SmartHome from a config entry."""
    session = aiohttp_client.async_get_clientsession(hass)
    
    api_client = WattsApiClient(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=session,
    )

    try:
        # Authenticate on setup
        await api_client.async_login()
    except WattsApiError as err:
        raise ConfigEntryNotReady(f"Failed to authenticate: {err}") from err

    # Get polling interval from options or use default
    polling_interval = entry.options.get(
        CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
    )

    coordinator = WattsCoordinator(
        hass,
        api_client,
        update_interval=timedelta(seconds=polling_interval),
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_API_CLIENT: api_client,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    async def handle_apply_program(call: ServiceCall) -> None:
        """Handle the apply_program service call."""
        device_id = call.data["device_id"]
        program_data = call.data["program_data"]
        lang = call.data.get("lang", DEFAULT_LANG)

        try:
            await api_client.async_apply_program(device_id, program_data, lang)
            _LOGGER.info("Applied program to device %s", device_id)
            # Trigger coordinator update to reflect changes
            await coordinator.async_request_refresh()
        except WattsApiError as err:
            _LOGGER.error("Failed to apply program to device %s: %s", device_id, err)

    async def handle_convert_program(call: ServiceCall) -> None:
        """Handle the convert_program service call."""
        program_data = call.data["program_data"]
        lang = call.data.get("lang", DEFAULT_LANG)

        try:
            result = await api_client.async_convert_program(program_data, lang)
            _LOGGER.info("Converted program: %s", result)
        except WattsApiError as err:
            _LOGGER.error("Failed to convert program: %s", err)

    async def handle_update_now(call: ServiceCall) -> None:
        """Handle the update_now service call."""
        await coordinator.async_request_refresh()
        _LOGGER.info("Triggered manual update")

    # Register services only once
    if not hass.services.has_service(DOMAIN, SERVICE_APPLY_PROGRAM):
        hass.services.async_register(
            DOMAIN,
            SERVICE_APPLY_PROGRAM,
            handle_apply_program,
            schema=SERVICE_APPLY_PROGRAM_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_CONVERT_PROGRAM):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CONVERT_PROGRAM,
            handle_convert_program,
            schema=SERVICE_CONVERT_PROGRAM_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_NOW):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_NOW,
            handle_update_now,
        )

    # Update listener for options
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        # Close the API client if it owns its session
        # api_client = data[DATA_API_CLIENT]
        # We're using the HA session, so we don't close it

    # Only remove services if no other entries remain
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_APPLY_PROGRAM)
        hass.services.async_remove(DOMAIN, SERVICE_CONVERT_PROGRAM)
        hass.services.async_remove(DOMAIN, SERVICE_UPDATE_NOW)

    return unload_ok
