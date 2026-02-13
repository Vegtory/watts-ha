"""Constants for the Watts SmartHome integration."""

DOMAIN = "watts_smarthome"

# API URLs
AUTH_BASE_URL = "https://auth.smarthome.wattselectronics.com"
API_BASE_URL = "https://smarthome.wattselectronics.com"
TOKEN_ENDPOINT = f"{AUTH_BASE_URL}/realms/watts/protocol/openid-connect/token"

# OAuth2 constants
CLIENT_ID = "app-front"
GRANT_TYPE_PASSWORD = "password"
GRANT_TYPE_REFRESH = "refresh_token"

# Configuration
CONF_POLLING_INTERVAL = "polling_interval"
DEFAULT_POLLING_INTERVAL = 60  # seconds
MIN_POLLING_INTERVAL = 30
MAX_POLLING_INTERVAL = 3600

# Platforms
PLATFORMS = ["sensor", "select", "number"]

# Coordinator data keys
DATA_COORDINATOR = "coordinator"
DATA_API_CLIENT = "api_client"

# API endpoints
ENDPOINT_USER_READ = "/api/v0.1/human/user/read/"
ENDPOINT_SMARTHOME_READ = "/api/v0.1/human/smarthome/read/"
ENDPOINT_GET_ERRORS = "/api/v0.1/human/smarthome/get_errors/"
ENDPOINT_CHECK_LAST_CONNEXION = "/api/v0.1/human/sandbox/check_last_connexion/"
ENDPOINT_STATS_READ = "/api/v0.1/human/stats/read/"
ENDPOINT_APPLY_PROGRAM = "/api/v0.1/human/device/apply_program/"
ENDPOINT_CONVERT_PROGRAM = "/api/v0.1/human/sandbox/convert_program/"
ENDPOINT_QUERY_PUSH = "/api/v0.1/human/query/push/"
ENDPOINT_TIME_OFFSET = "/api/v0.1/human/smarthome/time_offset/"

# Service names
SERVICE_APPLY_PROGRAM = "apply_program"
SERVICE_SET_WEEKLY_PROGRAM = "set_weekly_program"
SERVICE_CONVERT_PROGRAM = "convert_program"
SERVICE_UPDATE_NOW = "update_now"

# Default language
DEFAULT_LANG = "en"
