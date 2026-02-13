"""DataUpdateCoordinator for Watts SmartHome."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WattsApiClient, WattsApiError, WattsAuthError
from .const import DEFAULT_LANG, DOMAIN

_LOGGER = logging.getLogger(__name__)


class WattsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching Watts SmartHome data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: WattsApiClient,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.api_client = api_client
        self._smarthomes: list[dict[str, Any]] = []

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            # Get user data and smarthomes list
            user_response = await self.api_client.async_get_user_data(lang=DEFAULT_LANG)
            
            if "data" not in user_response:
                raise UpdateFailed("Invalid response from user API")

            user_data = user_response["data"]
            self._smarthomes = user_data.get("smarthomes", [])

            # Fetch data for all smarthomes
            smarthome_data = {}
            for smarthome in self._smarthomes:
                smarthome_id = smarthome.get("smarthome_id")
                if not smarthome_id:
                    continue

                try:
                    # Fetch smarthome details (zones and devices)
                    smarthome_response = await self.api_client.async_get_smarthome_data(
                        smarthome_id, lang=DEFAULT_LANG
                    )
                    
                    # Fetch errors
                    errors_response = await self.api_client.async_get_errors(
                        smarthome_id, lang=DEFAULT_LANG
                    )
                    
                    # Fetch last connection
                    last_conn_response = await self.api_client.async_check_last_connection(
                        smarthome_id, lang=DEFAULT_LANG
                    )

                    smarthome_data[smarthome_id] = {
                        "info": smarthome,
                        "details": smarthome_response.get("data", {}),
                        "errors": errors_response.get("data", {}),
                        "last_connection": last_conn_response.get("data", {}),
                    }

                except WattsApiError as err:
                    _LOGGER.warning(
                        "Error fetching data for smarthome %s: %s", smarthome_id, err
                    )
                    # Continue with other smarthomes even if one fails
                    smarthome_data[smarthome_id] = {
                        "info": smarthome,
                        "error": str(err),
                    }

            return {
                "user": user_data,
                "smarthomes": smarthome_data,
            }

        except WattsAuthError as err:
            raise UpdateFailed(f"Authentication error: {err}") from err
        except WattsApiError as err:
            raise UpdateFailed(f"API error: {err}") from err

    @property
    def smarthomes(self) -> list[dict[str, Any]]:
        """Return list of smarthomes."""
        return self._smarthomes

    def get_smarthome_data(self, smarthome_id: str) -> dict[str, Any] | None:
        """Get data for a specific smarthome."""
        if not self.data:
            return None
        return self.data.get("smarthomes", {}).get(smarthome_id)

    def get_device_data(self, smarthome_id: str, device_id: str) -> dict[str, Any] | None:
        """Get data for a specific device."""
        smarthome_data = self.get_smarthome_data(smarthome_id)
        if not smarthome_data:
            return None

        details = smarthome_data.get("details", {})
        zones = details.get("zones", [])
        
        for zone in zones:
            for device in zone.get("devices", []):
                if device.get("id_device") == device_id or device.get("id") == device_id:
                    return device
        
        return None
