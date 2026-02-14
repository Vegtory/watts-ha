"""The Watts SmartHome integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WattsApiClient, WattsApiError
from .const import (
    CONF_LANG,
    CONF_SCAN_INTERVAL,
    DEFAULT_LANG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICE_ATTR_ENTRY_ID,
    SERVICE_UPDATE_NOW,
)
from .coordinator import WattsDataUpdateCoordinator

UPDATE_NOW_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_ATTR_ENTRY_ID): cv.string,
    }
)


@dataclass
class WattsRuntimeData:
    """Runtime objects for a config entry."""

    api: WattsApiClient
    coordinator: WattsDataUpdateCoordinator


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration from YAML (unused)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Watts SmartHome from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    api = WattsApiClient(
        session=async_get_clientsession(hass),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        lang=entry.options.get(CONF_LANG, DEFAULT_LANG),
    )

    coordinator = WattsDataUpdateCoordinator(
        hass,
        api,
        update_interval_seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except WattsApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    hass.data[DOMAIN][entry.entry_id] = WattsRuntimeData(api=api, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_ensure_update_service(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    if not hass.data[DOMAIN] and hass.services.has_service(DOMAIN, SERVICE_UPDATE_NOW):
        hass.services.async_remove(DOMAIN, SERVICE_UPDATE_NOW)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_ensure_update_service(hass: HomeAssistant) -> None:
    """Register domain service(s) once."""
    if hass.services.has_service(DOMAIN, SERVICE_UPDATE_NOW):
        return

    async def async_handle_update_now(call: ServiceCall) -> None:
        runtimes: dict[str, WattsRuntimeData] = hass.data.get(DOMAIN, {})
        entry_id = call.data.get(SERVICE_ATTR_ENTRY_ID)

        if entry_id:
            runtime = runtimes.get(entry_id)
            if runtime is None:
                raise HomeAssistantError(f"Unknown Watts config entry id: {entry_id}")
            await runtime.coordinator.async_request_refresh()
            return

        await asyncio.gather(
            *(runtime.coordinator.async_request_refresh() for runtime in runtimes.values())
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_NOW,
        async_handle_update_now,
        schema=UPDATE_NOW_SCHEMA,
    )
