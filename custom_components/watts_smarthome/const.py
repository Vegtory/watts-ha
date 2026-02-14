"""Constants for the Watts SmartHome integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "watts_smarthome"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER]

API_BASE_URL = "https://smarthome.wattselectronics.com"
AUTH_BASE_URL = "https://auth.smarthome.wattselectronics.com"

AUTH_TOKEN_ENDPOINT = "/realms/watts/protocol/openid-connect/token"

ENDPOINT_USER_READ = "/api/v0.1/human/user/read/"
ENDPOINT_SMARTHOME_READ = "/api/v0.1/human/smarthome/read/"
ENDPOINT_QUERY_PUSH = "/api/v0.1/human/query/push/"

DEFAULT_LANG = "en_GB"
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 3600

DEFAULT_CONTEXT = "1"
DEFAULT_PEREMPTION_MS = 15000

CONF_LANG = "lang"
CONF_SCAN_INTERVAL = "scan_interval"

SERVICE_UPDATE_NOW = "update_now"
SERVICE_ATTR_ENTRY_ID = "entry_id"

DEFAULT_MIN_TEMP_C = 5.0
DEFAULT_MAX_TEMP_C = 35.0

MODE_OPTION_OFF = "Off"
MODE_OPTION_COMFORT = "Comfort"
MODE_OPTION_ECO = "Eco"
MODE_OPTION_ANTI_FROST = "Anti-frost"
MODE_OPTION_BOOST = "Boost"
MODE_OPTION_AUTO = "Auto"

MODE_OPTION_TO_CODE: dict[str, str] = {
    MODE_OPTION_OFF: "1",
    MODE_OPTION_COMFORT: "0",
    MODE_OPTION_ECO: "3",
    MODE_OPTION_ANTI_FROST: "2",
    MODE_OPTION_BOOST: "4",
    MODE_OPTION_AUTO: "13",
}

MODE_CODE_TO_OPTION: dict[str, str] = {
    "0": MODE_OPTION_COMFORT,
    "1": MODE_OPTION_OFF,
    "2": MODE_OPTION_ANTI_FROST,
    "3": MODE_OPTION_ECO,
    "4": MODE_OPTION_BOOST,
    "8": MODE_OPTION_AUTO,
    "11": MODE_OPTION_AUTO,
    "12": MODE_OPTION_COMFORT,
    "13": MODE_OPTION_AUTO,
    "14": MODE_OPTION_OFF,
}

MODE_CODE_TO_LABEL: dict[str, str] = {
    "0": "comfort",
    "1": "off",
    "2": "anti-frost",
    "3": "eco",
    "4": "boost",
    "8": "auto-comfort",
    "11": "auto-eco",
    "12": "on",
    "13": "auto",
    "14": "disabled",
}
