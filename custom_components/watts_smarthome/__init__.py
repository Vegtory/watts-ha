"""The Watts SmartHome integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import WattsApiClient
from .const import CONF_LANG, CONF_SCAN_INTERVAL, DEFAULT_LANG, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import WattsDataUpdateCoordinator
from .data import WattsRuntimeData

PLATFORMS: tuple[Platform, ...] = (
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Watts integration from YAML (not used)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Watts SmartHome from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    lang = entry.options.get(CONF_LANG, entry.data.get(CONF_LANG, DEFAULT_LANG))
    scan_interval = int(
        entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
    )

    session = async_get_clientsession(hass)
    client = WattsApiClient(
        session=session,
        username=username,
        password=password,
        default_lang=lang,
    )
    coordinator = WattsDataUpdateCoordinator(
        hass,
        client=client,
        lang=lang,
        scan_interval_seconds=scan_interval,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = WattsRuntimeData(
        client=client,
        coordinator=coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


def get_runtime_data(hass: HomeAssistant, entry: ConfigEntry) -> WattsRuntimeData:
    """Return runtime data for a config entry."""
    return hass.data[DOMAIN][entry.entry_id]


def get_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> WattsDataUpdateCoordinator:
    """Return coordinator for a config entry."""
    return get_runtime_data(hass, entry).coordinator


def get_client(hass: HomeAssistant, entry: ConfigEntry) -> WattsApiClient:
    """Return API client for a config entry."""
    return get_runtime_data(hass, entry).client
