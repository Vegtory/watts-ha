# Watts SmartHome Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

A custom Home Assistant integration for Watts SmartHome heating control systems.

## Features

- **Full UI Configuration** - Set up via the Home Assistant UI (Config Flow)
- **Automatic Token Management** - Handles authentication and token refresh automatically
- **Multiple Accounts** - Support for multiple Watts SmartHome accounts
- **Comprehensive Entity Support**:
  - Temperature sensors (air and floor)
  - Setpoint sensors (comfort, eco, manual)
  - Status sensors (heating status, error codes, last connection)
  - Mode selectors for operating modes
  - Manual setpoint controls
- **Services**:
  - Apply heating programs to devices
  - Convert programs to UI-friendly format
  - Manual data refresh
- **Device Registry Integration** - All entities are properly grouped by device
- **Diagnostics** - Built-in diagnostics with sensitive data redaction
- **Configurable Polling** - Adjust update interval (30-3600 seconds, default 60s)

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner and select "Custom repositories"
4. Add this repository URL: `https://github.com/Vegtory/watts-ha`
5. Select category "Integration"
6. Click "Add"
7. Find "Watts SmartHome" in the integration list
8. Click "Download"
9. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/watts_smarthome` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Watts SmartHome"
4. Enter your Watts SmartHome credentials (email and password)
5. Click **Submit**

The integration will authenticate with the Watts SmartHome cloud API and discover your devices automatically.

### Options

After setup, you can configure additional options:

- **Polling Interval**: How often to fetch data from the API (30-3600 seconds, default 60s)

To change options:
1. Go to **Settings** → **Devices & Services**
2. Find "Watts SmartHome"
3. Click **Configure**

## Entities

The integration creates the following entities for each smarthome:

### Smarthome-Level Entities
- **General Mode** - Current operating mode
- **Holiday Mode** - Holiday mode status
- **Last Connection** - Time since last connection (seconds)
- **Error Count** - Number of active errors

### Device-Level Entities

For each heating device/zone:

#### Sensors
- **Air Temperature** - Current air temperature
- **Floor Temperature** - Current floor temperature (if available)
- **Comfort Setpoint** - Comfort mode target temperature
- **Eco Setpoint** - Eco mode target temperature
- **Heating Status** - Whether the device is actively heating
- **Error Code** - Device error code (0 = no error)
- **Operating Mode** - Current device mode
- **Program** - Active program name

#### Controls
- **Mode Selector** - Change operating mode (Comfort, Eco, Program, etc.)
- **Manual Setpoint** - Set target temperature in manual mode

## Services

### `watts_smarthome.apply_program`

Apply a weekly heating program to a device.

**Parameters:**
- `device_id` (required): Device ID
- `program_data` (required): Program data as dictionary
- `lang` (optional): Language code (default: "en")

**Example:**
```yaml
service: watts_smarthome.apply_program
data:
  device_id: "12345"
  program_data:
    "program[monday][0][start]": "08:00"
    "program[monday][0][end]": "22:00"
    "program[monday][0][value]": "20"
```

### `watts_smarthome.convert_program`

Convert a device program into UI-friendly time blocks.

**Parameters:**
- `program_data` (required): Raw program data
- `lang` (optional): Language code (default: "en")

### `watts_smarthome.update_now`

Trigger an immediate data refresh.

**Example:**
```yaml
service: watts_smarthome.update_now
```

## API Details

This integration communicates with the Watts SmartHome cloud API:
- **Auth Server**: `https://auth.smarthome.wattselectronics.com`
- **API Server**: `https://smarthome.wattselectronics.com`

Authentication uses OAuth2 Resource Owner Password Credentials flow via Keycloak.

## Troubleshooting

### Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.watts_smarthome: debug
```

### Common Issues

**"Invalid username or password"**
- Verify your credentials are correct
- Check if you can log in via the Watts SmartHome mobile app

**"Cannot connect to API"**
- Check your internet connection
- Verify Home Assistant can reach `smarthome.wattselectronics.com`

**Entities not updating**
- Check the polling interval in Options
- View the integration logs for errors
- Use the `update_now` service to force a refresh

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/Vegtory/watts-ha/issues).

## License

This integration is provided as-is without warranty. Use at your own risk.

## Credits

Developed for the Home Assistant community. Not affiliated with or endorsed by Watts Electronics.
