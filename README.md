# Watts SmartHome for Home Assistant

<img src="custom_components/watts_smarthome/logo.svg" alt="Watts SmartHome integration icon" width="128">

Custom HACS integration for Watts Electronics SmartHome thermostats (cloud).

## Entities

Per thermostat:

| Entity | Notes |
|---|---|
| `climate` | **Auto** = weekly schedule, **Heat** = fixed preset, **Off**. Presets: comfort, eco, anti-frost, boost. |
| `binary_sensor` Problem | On when the thermostat reports a fault; the `errors` attribute names it (for example "Battery failure"). |
| `number` Comfort / Eco / Anti-frost / Boost temperature | Setpoint per mode (configuration). |
| `number` Boost duration | Used when boost is started from Home Assistant. Changing it while boost runs restarts boost. |
| `sensor` Next schedule change | While in Auto: when the schedule next switches, with `next_period` and `next_temperature`. |
| `sensor` Air temperature, Heating status | |
| `sensor` Floor temperature | Disabled by default; empty when there is no floor sensor. |
| `select` Mode | Disabled by default (the thermostat covers it). Enable it for automations that pick a mode by name. |
| `sensor` Operating mode | Diagnostic. |
| `sensor` Error code | Diagnostic, disabled by default (the Problem sensor shows the same faults). |

### Using the thermostat

- **Auto (schedule):** there is no temperature dial, because the schedule switches between the comfort
  and eco temperatures (the Watts app works the same way). The thermostat shows what the schedule is doing:
  `schedule_period` / `schedule_temperature` (now) and `next_change` / `next_period` / `next_temperature`
  (next switch). The schedule itself is edited in the Watts app. To run the schedule in Home Assistant
  instead, keep the thermostat in Heat and switch the Comfort/Eco presets with a Schedule helper and an
  automation.
- **Temperatures** use 0.5 °C steps, like the thermostat. Values from automations are rounded to the
  nearest 0.5 °C.
- **To set a temperature:** choose **Heat**, which starts in Comfort, then turn the dial. The dial changes the
  temperature of the active preset, so with Comfort active it changes the Comfort temperature, which the
  schedule also uses. To change the schedule temperatures without leaving Auto, use the Comfort / Eco
  temperature controls.
- Presets are in the thermostat dialog. To show them on a dashboard card, add the *Climate preset modes* feature:

  ```yaml
  type: thermostat
  entity: climate.living_room
  features:
    - type: climate-hvac-modes
    - type: climate-preset-modes
      style: icons
  ```

- If a change does not reach the thermostat, Home Assistant shows a notification naming the room and the
  change, and the thermostat shows its previous settings again.

Per central unit:

| Entity | Notes |
|---|---|
| `binary_sensor` Central unit connection | Off when the central unit has not checked in for 60 s. Commands are refused then. |
| `sensor` Last command | `delivered`, `failed`, `sent` (waiting), … |
| `sensor` Last check-in | Seconds since the central unit contacted the cloud (disabled by default). |

## How commands are synced

The integration follows the same protocol as the official web app:

1. Changes show in Home Assistant at once. Quick successive changes to one thermostat are merged into one command.
2. Before sending, the central unit must have checked in within the last 60 s.
3. The command is queued in the Watts cloud with a 15 s timeout (`peremption`).
4. For 15 s after sending, no state is read (the cloud still returns old values then).
5. After the timeout, `query/check_failure` tells whether the central unit picked the command up.
   On failure the change is rolled back, a notification names what was not applied, and the next timeout is
   longer (up to 30 s).
6. Home Assistant reads again every 10 s until the thermostat reports the new values.

Changes are refused while holiday mode is active, like in the app.

## Polling

- Thermostat state: every 60 s by default (Options, minimum 30 s).
- Smarthome list: every 10 minutes.

## Installation (HACS)

1. Add this repository as a custom HACS repository (category: Integration).
2. Install **Watts SmartHome** from HACS and restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Watts SmartHome**, then sign in with your Watts account.

Requires Home Assistant 2025.1 or newer.
The integration icon in Home Assistant (light and dark, in `brand/`) shows from Home Assistant 2026.3.

## Options

- **Language**: language for texts from the Watts cloud, such as error titles (default `en_GB`).
- **Polling interval**: seconds between reads (default 60).

If the password changes, Home Assistant asks you to sign in again. Use **Reconfigure** to change the account e-mail.

## Removal

**Settings → Devices & Services → Watts SmartHome → ⋮ → Delete**, then remove it in HACS.

## Development

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

`scripts/dump_responses.py` saves real API responses to `.responses/` (credentials from `.env`).
It only sends test writes when `WATTS_DUMP_PUSH=1` is set. Never commit `.responses/`, `.env` or `.har` files:
they contain tokens and personal data.
