# Watts SmartHome for Home Assistant

![Watts logo](custom_components/watts_smarthome/logo.svg)

Version: `v0.0.1`

Custom HACS integration for Watts Electronics SmartHome thermostats.

## Features

- OAuth login against Watts Keycloak endpoint.
- Polling coordinator that loads:
  - user profile and smarthome list
  - full smarthome state (zones + devices)
  - device error details
- Domain models for all core Watts entities:
  - user profile
  - smarthome summary
  - smarthome
  - zone
  - mode metadata
  - device
  - device error

## Exposed Home Assistant entities

### Controls

- `select`: mode selection
- `number`: setpoint comfort
- `number`: setpoint eco
- `number`: setpoint anti-frost
- `number`: setpoint boost
- `number`: boost timer (seconds)

### Sensors

- `sensor`: current air temperature
- `sensor`: heating status
- `sensor`: error code
- `sensor`: operating mode

## Installation (HACS)

1. Add this repository as a custom HACS repository (category: Integration).
2. Install **Watts SmartHome** from HACS.
3. Restart Home Assistant.
4. Add integration: **Settings -> Devices & Services -> Add Integration -> Watts SmartHome**.
5. Enter your Watts account email/password.

## Configuration options

- `Language` (default: `en_GB`)
- `Polling interval (seconds)` (default: `60`, minimum `15`)

## Notes

- Setpoint and temperature values are converted between Watts raw units and Celsius.
- Writes are sent via `/api/v0.1/human/query/push/` with `query[...]` payload fields.
- After each control write, coordinator refresh is requested to sync state.
