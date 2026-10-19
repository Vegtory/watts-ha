"""Constants for the Watts SmartHome integration."""

from __future__ import annotations

DOMAIN = "watts_smarthome"
MANUFACTURER = "Watts Electronics"

API_BASE_URL = "https://smarthome.wattselectronics.com"
AUTH_BASE_URL = "https://auth.smarthome.wattselectronics.com"
TOKEN_PATH = "/realms/watts/protocol/openid-connect/token"
TOKEN_CLIENT_ID = "app-front"

DEFAULT_LANG = "en_GB"
CONF_LANG = "lang"

DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
CONF_SCAN_INTERVAL = "scan_interval"

REQUEST_TOKEN_LITERAL = "true"
REQUEST_CONTEXT = "1"

# --- Command sync timing -----------------------------------------------------
# Mirrors the official web app (scripts.js, config block):
#   theoricsTimesExecutions  [15e3, 2e4, 25e3, 3e4]  -> peremption steps (ms)
#   delayQueryExecution      15 s                    -> no reads right after a push
#   delayAlertLastConnexion  60 s                    -> refuse to send if central is silent
# The cloud keeps a pushed command for `peremption` ms. The central unit picks it
# up on its next check-in (every ~10-15 s). After that window, query/check_failure
# tells whether the command expired undelivered.
PEREMPTION_STEPS_MS: tuple[int, ...] = (15000, 20000, 25000, 30000)
# Wait this long after the peremption window before asking check_failure.
CHECK_FAILURE_MARGIN_SECONDS = 1.0
# Do not read state for this long after a push: the cloud still returns old values.
POST_WRITE_QUIET_SECONDS = 15.0
# Extra refreshes after the check, until the cloud reflects the command.
CONFIRM_RETRY_INTERVAL_SECONDS = 10.0
# Stop waiting for confirmation this long after the peremption window ended.
CONFIRM_TIMEOUT_SECONDS = 45.0
# Collect quick successive writes to one device into a single push.
WRITE_DEBOUNCE_SECONDS = 1.0
# Refuse to send commands when the central unit has been silent this long.
MAX_CENTRAL_SILENCE_SECONDS = 60
# Reuse a fresh check_last_connexion result for this long before a push.
CONNECTION_CHECK_CACHE_SECONDS = 10.0
# The smarthome list (user/read) rarely changes; reload it this often.
USER_REFRESH_INTERVAL_SECONDS = 600

# --- Temperatures --------------------------------------------------------------
# Watts sends temperatures/setpoints as deci-Fahrenheit (446 = 44.6 F = 7.0 C).
RAW_TEMPERATURE_DECI_SCALE = 10.0
FAHRENHEIT_OFFSET = 32.0
FAHRENHEIT_TO_CELSIUS_FACTOR = 5.0 / 9.0
CELSIUS_TO_FAHRENHEIT_FACTOR = 9.0 / 5.0
# Values outside this range mean "no sensor" (the app shows --.-; 2124 is common).
VALID_TEMPERATURE_MIN_C = -60.0
VALID_TEMPERATURE_MAX_C = 100.0
TEMPERATURE_STEP_C = 0.5
ANTI_FROST_MIN_C = 0.5
ANTI_FROST_MAX_C = 10.0

# --- Modes (gv_mode / nv_mode codes, see the app's mode switch) ---------------
MODE_COMFORT = "comfort"
MODE_OFF = "off"
MODE_ANTI_FROST = "anti_frost"
MODE_ECO = "eco"
MODE_BOOST = "boost"
MODE_PROGRAM_ON = "program_on"  # schedule, currently in a comfort period
MODE_PROGRAM_ECO = "program_eco"  # schedule, currently in an eco period
MODE_PROGRAM = "program"  # schedule, other period
MODE_MANUAL = "manual"
MODE_PROGRAM_BOOST = "program_boost"  # schedule, boost active
MODE_UNKNOWN = "unknown"

MODE_CODE_TO_OPTION: dict[str, str] = {
    "0": MODE_COMFORT,
    "1": MODE_OFF,
    "2": MODE_ANTI_FROST,
    "3": MODE_ECO,
    "4": MODE_BOOST,
    "8": MODE_PROGRAM_ON,
    "11": MODE_PROGRAM_ECO,
    "13": MODE_PROGRAM,
    "15": MODE_MANUAL,
    "16": MODE_PROGRAM_BOOST,
}
MODE_OPTION_TO_CODE: dict[str, str] = {value: key for key, value in MODE_CODE_TO_OPTION.items()}

# Modes a user can pick. "program_on" (code 8) starts the schedule; the device
# then reports 8/11/13/16 depending on the active period.
SELECTABLE_MODES: tuple[str, ...] = (
    MODE_COMFORT,
    MODE_ECO,
    MODE_ANTI_FROST,
    MODE_BOOST,
    MODE_OFF,
    MODE_PROGRAM_ON,
)
PROGRAM_MODES: frozenset[str] = frozenset({MODE_PROGRAM_ON, MODE_PROGRAM_ECO, MODE_PROGRAM, MODE_PROGRAM_BOOST})
ALL_MODES: tuple[str, ...] = tuple(MODE_CODE_TO_OPTION.values())

# --- Raw device fields ---------------------------------------------------------
FIELD_ID_DEVICE = "id_device"
FIELD_GV_MODE = "gv_mode"
FIELD_NV_MODE = "nv_mode"
FIELD_PROGRAMME = "programme"
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

# Setpoint a mode uses (the app's `consigne_to_get`).
SETPOINT_BY_MODE: dict[str, str] = {
    MODE_COMFORT: SETPOINT_COMFORT,
    MODE_ECO: SETPOINT_ECO,
    MODE_ANTI_FROST: SETPOINT_ANTI_FROST,
    MODE_BOOST: SETPOINT_BOOST,
    MODE_PROGRAM_ON: SETPOINT_COMFORT,
    MODE_PROGRAM_ECO: SETPOINT_ECO,
    MODE_MANUAL: SETPOINT_MANUAL,
    MODE_PROGRAM_BOOST: SETPOINT_BOOST,
}

# English labels for notifications (entity states are translated via strings.json).
MODE_LABELS: dict[str, str] = {
    MODE_COMFORT: "Comfort",
    MODE_OFF: "Off",
    MODE_ANTI_FROST: "Anti-frost",
    MODE_ECO: "Eco",
    MODE_BOOST: "Boost",
    MODE_PROGRAM_ON: "Schedule",
    MODE_PROGRAM_ECO: "Schedule",
    MODE_PROGRAM: "Schedule",
    MODE_MANUAL: "Manual",
    MODE_PROGRAM_BOOST: "Schedule (boost)",
}
SETPOINT_LABELS: dict[str, str] = {
    SETPOINT_COMFORT: "comfort temperature",
    SETPOINT_ECO: "eco temperature",
    SETPOINT_ANTI_FROST: "anti-frost temperature",
    SETPOINT_BOOST: "boost temperature",
}

DEFAULT_BOOST_SECONDS = 3600
MIN_BOOST_SECONDS = 180  # app: timerMinDuration
MAX_BOOST_SECONDS = 7 * 24 * 3600

HEATING_IDLE = "idle"
HEATING_ACTIVE = "heating"

CONF_ENTRY_TITLE_FALLBACK = "Watts SmartHome"
