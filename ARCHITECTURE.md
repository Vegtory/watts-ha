# Watts SmartHome Integration - Architecture

## Overview

This integration provides full Home Assistant support for Watts SmartHome heating control systems via their cloud API.

## Component Architecture

### 1. API Client (`api.py`)
- **OAuth2 Authentication**: Password grant flow with Keycloak
- **Token Management**: Automatic refresh with fallback to re-login
- **Retry Logic**: Configurable retries with exponential backoff
- **Endpoints Covered**:
  - User data and smarthome list
  - Smarthome details (zones/devices)
  - Error reporting
  - Last connection status
  - Time offset
  - Program management (apply/convert)
  - Device query/command

### 2. Data Coordinator (`coordinator.py`)
- **Polling Strategy**: Configurable interval (30-3600s, default 60s)
- **Data Normalization**: Fetches and structures data from multiple endpoints
- **Error Handling**: Graceful degradation - continues with other smarthomes if one fails
- **Helper Methods**: Easy access to smarthome and device data

### 3. Config Flow (`config_flow.py`)
- **UI Setup**: Username/password form with validation
- **Duplicate Prevention**: Unique ID based on username
- **Options Flow**: Adjustable polling interval
- **Validation**: Tests auth and API connectivity on setup

### 4. Entity Platforms

#### Sensors (`sensor.py`)
- **Smarthome Level**: General mode, holiday mode, last connection, error count
- **Device Level**: Temperatures (air/floor), setpoints (comfort/eco/manual), heating status, error code, operating mode, program

#### Select (`select.py`)
- **Operating Mode**: Off, Comfort, Eco, Frost Protection, Program
- **API Integration**: Uses query/push endpoint to change modes

#### Number (`number.py`)
- **Manual Setpoint**: Adjustable temperature with device-specific min/max
- **API Integration**: Uses query/push endpoint to set temperature

### 5. Services
- **apply_program**: Apply weekly heating schedule to device
- **convert_program**: Convert raw program data to UI format
- **update_now**: Force immediate data refresh

### 6. Diagnostics (`diagnostics.py`)
- **Data Export**: Full coordinator data for troubleshooting
- **Redaction**: Removes sensitive data (emails, IDs, locations)

## Data Flow

```
User Setup
    ↓
ConfigFlow validates credentials
    ↓
Integration creates API client and coordinator
    ↓
Coordinator polls API every N seconds
    ↓
Entities update from coordinator data
    ↓
User controls trigger API commands
    ↓
Coordinator refreshes to reflect changes
```

## API Integration Details

### Authentication Flow
1. Initial login: POST to `/realms/watts/protocol/openid-connect/token`
2. Store access_token and refresh_token
3. Before token expiry, refresh automatically
4. If refresh fails, perform new login

### Data Fetching
For each smarthome:
1. Fetch user data (smarthomes list)
2. For each smarthome:
   - Fetch smarthome details (zones/devices)
   - Fetch errors
   - Fetch last connection

### Command Execution
- Mode changes: Use `query/push` endpoint with `query[gv_mode]`
- Setpoint changes: Use `query/push` endpoint with `query[consigne_manuel]`
- Program application: Use `device/apply_program` endpoint

## Device Registry

Entities are grouped into devices:
- **Smarthome Device**: Groups smarthome-level sensors
- **Zone/Device**: Groups device-level sensors and controls
- **Hierarchy**: Devices are linked via `via_device` to smarthome

## Security Features

1. **No Credential Logging**: Passwords and tokens never logged
2. **Token Redaction**: Diagnostics redacts all sensitive data
3. **Secure Storage**: Credentials stored in HA's encrypted config entries
4. **HTTPS Only**: All API calls over secure connections

## Testing

Tests cover:
- API client authentication and token refresh
- Config flow validation and error handling
- Integration setup and teardown
- Mock responses for all API calls

## Future Enhancements

Potential additions:
- Climate entity (unified temperature control)
- Binary sensors for heating state
- Energy monitoring if API provides data
- Advanced program editor UI
- Multi-zone program synchronization
