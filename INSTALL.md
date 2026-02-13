# Installation and Testing Guide

## Prerequisites

- Home Assistant 2023.8.0 or later
- HACS (Home Assistant Community Store) installed
- Watts SmartHome account credentials

## Installation Methods

### Method 1: HACS (Recommended)

1. **Add Custom Repository**
   - Open HACS in Home Assistant
   - Click on "Integrations"
   - Click the three dots (⋮) in the top right
   - Select "Custom repositories"
   - Add repository URL: `https://github.com/Vegtory/watts-ha`
   - Category: "Integration"
   - Click "Add"

2. **Install Integration**
   - Find "Watts SmartHome" in HACS
   - Click "Download"
   - Restart Home Assistant

3. **Configure Integration**
   - Go to Settings → Devices & Services
   - Click "+ Add Integration"
   - Search for "Watts SmartHome"
   - Enter your credentials
   - Submit

### Method 2: Manual Installation

1. **Copy Files**
   ```bash
   cd /config
   mkdir -p custom_components
   cd custom_components
   git clone https://github.com/Vegtory/watts-ha.git
   cp -r watts-ha/custom_components/watts_smarthome ./
   ```

2. **Restart Home Assistant**

3. **Configure** (same as HACS method step 3)

## Configuration Options

After initial setup, you can configure:

- **Polling Interval**: 30-3600 seconds (default: 60)
  - Settings → Devices & Services → Watts SmartHome → Configure

## Verifying Installation

### Check Integration Loaded

1. Go to Settings → System → Logs
2. Search for "watts_smarthome"
3. Should see: "Successfully authenticated" and "Setup of domain watts_smarthome took X seconds"

### Check Entities Created

1. Go to Settings → Devices & Services
2. Click on "Watts SmartHome"
3. You should see:
   - At least one device per smarthome
   - Multiple sensors per device
   - Select and number entities for devices

### Example Entities

For a smarthome with one heating device, expect:
- `sensor.living_room_air_temperature`
- `sensor.living_room_comfort_setpoint`
- `sensor.living_room_heating_status`
- `select.living_room_mode`
- `number.living_room_manual_setpoint`
- And more...

## Testing Services

### Test Update Service

```yaml
service: watts_smarthome.update_now
```

Check logs to confirm data refresh.

### Test Mode Change

```yaml
service: select.select_option
target:
  entity_id: select.your_device_mode
data:
  option: "Comfort"
```

### Test Setpoint Change

```yaml
service: number.set_value
target:
  entity_id: number.your_device_manual_setpoint
data:
  value: 21.5
```

## Diagnostics

### Download Diagnostics

1. Settings → Devices & Services → Watts SmartHome
2. Click on your smarthome device
3. Click "Download diagnostics"
4. Review redacted data

### Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.watts_smarthome: debug
    custom_components.watts_smarthome.api: debug
```

Restart and check logs at Settings → System → Logs.

## Troubleshooting

### "Cannot connect to API"

**Symptoms**: Integration fails to set up with connection error.

**Solutions**:
1. Check internet connectivity
2. Verify Home Assistant can reach external URLs
3. Check firewall settings
4. Try manual API test:
   ```bash
   curl -X POST https://auth.smarthome.wattselectronics.com/realms/watts/protocol/openid-connect/token \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "grant_type=password&username=YOUR_EMAIL&password=YOUR_PASSWORD&client_id=app-front"
   ```

### "Invalid username or password"

**Symptoms**: Authentication fails during setup.

**Solutions**:
1. Verify credentials work in Watts mobile app
2. Check for special characters in password (may need URL encoding)
3. Ensure using email address as username

### Entities Not Updating

**Symptoms**: Entity states are stale or unavailable.

**Solutions**:
1. Check coordinator update interval in options
2. Verify API rate limits aren't exceeded
3. Check logs for API errors
4. Try manual refresh: `watts_smarthome.update_now`

### Missing Entities

**Symptoms**: Expected entities don't appear.

**Solutions**:
1. Some entities only appear if device supports them
2. Check coordinator data in diagnostics
3. Verify device actually has the feature (e.g., floor temp sensor)

### Token Refresh Issues

**Symptoms**: Integration stops working after some time, logs show auth errors.

**Solutions**:
1. Integration should auto-refresh tokens
2. Check logs for refresh errors
3. Try reloading the integration
4. Re-authenticate if refresh consistently fails

## Development Testing

### Run Unit Tests

```bash
cd watts-ha
pip install -r requirements-test.txt
pytest tests/
```

### Test Individual Components

```python
# Test API client
python3 -c "
from custom_components.watts_smarthome.api import WattsApiClient
import asyncio

async def test():
    client = WattsApiClient('user@example.com', 'password')
    await client.async_login()
    data = await client.async_get_user_data()
    print(data)

asyncio.run(test())
"
```

## Monitoring

### Key Metrics to Monitor

- **Last Connection**: Should update regularly
- **Error Count**: Should stay at 0
- **Temperature Sensors**: Should match actual temperatures
- **Heating Status**: Should correlate with device activity

### Automation Examples

**Alert on Connection Loss**:
```yaml
automation:
  - alias: "Watts Connection Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.your_smarthome_last_connection
        above: 3600  # 1 hour
    action:
      - service: notify.mobile_app
        data:
          message: "Watts SmartHome hasn't connected in over an hour"
```

**Auto-adjust on Low Temperature**:
```yaml
automation:
  - alias: "Boost Heating When Cold"
    trigger:
      - platform: numeric_state
        entity_id: sensor.living_room_air_temperature
        below: 18
    action:
      - service: select.select_option
        target:
          entity_id: select.living_room_mode
        data:
          option: "Comfort"
```

## Support

For issues:
1. Check this guide
2. Review logs with debug enabled
3. Download diagnostics
4. Open issue at: https://github.com/Vegtory/watts-ha/issues

Include:
- Home Assistant version
- Integration version
- Relevant log excerpts (with secrets redacted)
- Diagnostics file
