"""Constants for the Watts SmartHome integration."""

from __future__ import annotations

DOMAIN = "watts_smarthome"

API_BASE_URL = "https://smarthome.wattselectronics.com"
AUTH_BASE_URL = "https://auth.smarthome.wattselectronics.com"
TOKEN_PATH = "/realms/watts/protocol/openid-connect/token"
TOKEN_GRANT_TYPE = "password"
TOKEN_CLIENT_ID = "app-front"

DEFAULT_LANG = "en_GB"
CONF_LANG = "lang"

DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 15
CONF_SCAN_INTERVAL = "scan_interval"

REQUEST_TOKEN_LITERAL = "true"
REQUEST_CONTEXT = "1"
REQUEST_PEREMPTION_MS = "15000"

# After sending a write command, poll faster for a short window to pick up
# device-side state changes sooner.
POST_WRITE_FAST_POLL_INTERVAL_SECONDS = 15
POST_WRITE_FAST_POLL_DURATION_SECONDS = 5 * 60

# Watts API temperatures/setpoints are observed as deci-Fahrenheit values
# (for example: 446 = 44.6F = 7.0C anti-frost).
RAW_TEMPERATURE_DECI_SCALE = 10.0
FAHRENHEIT_OFFSET = 32.0
FAHRENHEIT_TO_CELSIUS_FACTOR = 5.0 / 9.0
CELSIUS_TO_FAHRENHEIT_FACTOR = 9.0 / 5.0

MODE_COMFORT = "comfort"
MODE_OFF = "off"
MODE_ANTI_FROST = "anti_frost"
MODE_ECO = "eco"
MODE_BOOST = "boost"
MODE_PROGRAM_ON = "program_on"
MODE_MANUAL = "manual"
MODE_UNKNOWN = "unknown"

MODE_CODE_TO_OPTION: dict[str, str] = {
    "0": MODE_COMFORT,
    "1": MODE_OFF,
    "2": MODE_ANTI_FROST,
    "3": MODE_ECO,
    "4": MODE_BOOST,
    "8": MODE_PROGRAM_ON,
    "11": MODE_MANUAL,
}

MODE_OPTION_TO_CODE: dict[str, str] = {value: key for key, value in MODE_CODE_TO_OPTION.items()}
MODE_OPTIONS: tuple[str, ...] = (
    MODE_COMFORT,
    MODE_OFF,
    MODE_ANTI_FROST,
    MODE_ECO,
    MODE_BOOST,
    MODE_PROGRAM_ON,
    MODE_MANUAL,
)

SETPOINT_COMFORT = "consigne_confort"
SETPOINT_ECO = "consigne_eco"
SETPOINT_ANTI_FROST = "consigne_hg"
SETPOINT_BOOST = "consigne_boost"
SETPOINT_MANUAL = "consigne_manuel"
BOOST_TIMER = "time_boost"

SETPOINT_KEYS: tuple[str, ...] = (
    SETPOINT_COMFORT,
    SETPOINT_ECO,
    SETPOINT_ANTI_FROST,
    SETPOINT_BOOST,
)

SETPOINT_BY_MODE: dict[str, str] = {
    MODE_COMFORT: SETPOINT_COMFORT,
    MODE_ECO: SETPOINT_ECO,
    MODE_ANTI_FROST: SETPOINT_ANTI_FROST,
    MODE_BOOST: SETPOINT_BOOST,
}

HEATING_IDLE = "idle"
HEATING_ACTIVE = "heating"

CONF_ENTRY_TITLE_FALLBACK = "Watts SmartHome"
