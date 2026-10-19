"""The Watts SmartHome integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WattsApiClient
from .const import CONF_LANG, CONF_SCAN_INTERVAL, DEFAULT_LANG, DEFAULT_SCAN_INTERVAL, DOMAIN, MIN_SCAN_INTERVAL
from .coordinator import WattsDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]

type WattsConfigEntry = ConfigEntry[WattsDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: WattsConfigEntry) -> bool:
    """Set up Watts SmartHome from a config entry."""
    lang = entry.options.get(CONF_LANG, entry.data.get(CONF_LANG, DEFAULT_LANG))
    scan_interval = max(
        MIN_SCAN_INTERVAL,
        int(entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))),
    )

    client = WattsApiClient(
        session=async_get_clientsession(hass),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        default_lang=lang,
    )
    coordinator = WattsDataUpdateCoordinator(
        hass,
        entry,
        client=client,
        lang=lang,
        scan_interval_seconds=scan_interval,
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WattsConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: WattsConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: WattsConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow removing a device that the cloud no longer reports."""
    coordinator = entry.runtime_data
    known = {f"{sid}_{did}" for sid, did in coordinator.device_keys()} | coordinator.smarthome_ids()
    return not any(domain == DOMAIN and identifier in known for domain, identifier in device_entry.identifiers)
