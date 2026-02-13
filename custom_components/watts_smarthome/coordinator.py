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
                    smarthome_details = (
                        await self.api_client.async_get_smarthome_data(
                            smarthome_id, lang=DEFAULT_LANG
                        )
                    ).get("data", {})

                    errors_data = await self._safe_smarthome_call(
                        smarthome_id,
                        "errors",
                        self.api_client.async_get_errors(smarthome_id, lang=DEFAULT_LANG),
                    )
                    last_connection_data = await self._safe_smarthome_call(
                        smarthome_id,
                        "last_connection",
                        self.api_client.async_check_last_connection(
                            smarthome_id, lang=DEFAULT_LANG
                        ),
                    )
                    time_offset_data = await self._safe_smarthome_call(
                        smarthome_id,
                        "time_offset",
                        self.api_client.async_get_time_offset(smarthome_id, lang=DEFAULT_LANG),
                    )
                    stats_data = await self._safe_smarthome_call(
                        smarthome_id,
                        "stats",
                        self.api_client.async_get_stats(smarthome_id, lang=DEFAULT_LANG),
                    )
                    devices, devices_by_id = self._normalize_devices(
                        smarthome_id, smarthome_details, errors_data, stats_data
                    )

                    smarthome_data[smarthome_id] = {
                        "info": smarthome,
                        "details": smarthome_details,
                        "errors": errors_data,
                        "last_connection": last_connection_data,
                        "time_offset": time_offset_data,
                        "stats": stats_data,
                        "devices": devices,
                        "devices_by_id": devices_by_id,
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

    async def _safe_smarthome_call(
        self,
        smarthome_id: str,
        endpoint_name: str,
        call,
    ) -> dict[str, Any]:
        """Fetch optional smarthome data and return an empty dict on failure."""
        try:
            response = await call
        except WattsApiError as err:
            _LOGGER.debug(
                "Unable to fetch %s for smarthome %s: %s",
                endpoint_name,
                smarthome_id,
                err,
            )
            return {}

        if not isinstance(response, dict):
            return {}
        data = response.get("data")
        if not isinstance(data, dict):
            return {}
        return data

    @staticmethod
    def _resolve_device_id(raw_id: Any) -> str | None:
        """Normalize device IDs from id_device/id fields."""
        if raw_id in (None, ""):
            return None
        device_id = str(raw_id)
        if "#" in device_id:
            return device_id.split("#", 1)[1]
        return device_id

    @classmethod
    def _device_id_from_payload(cls, device: dict[str, Any]) -> str | None:
        """Extract normalized device ID from a device payload."""
        return cls._resolve_device_id(device.get("id_device") or device.get("id"))

    @staticmethod
    def _merge_non_empty(target: dict[str, Any], source: dict[str, Any]) -> None:
        """Merge source dict into target without overwriting useful values with empties."""
        for key, value in source.items():
            if key not in target:
                target[key] = value
                continue
            if target[key] in (None, "", []):
                target[key] = value
                continue
            if value not in (None, "", []):
                target[key] = value

    @classmethod
    def _normalize_devices(
        cls,
        smarthome_id: str,
        details: dict[str, Any],
        errors: dict[str, Any],
        stats: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        """Build a merged per-device view from details, errors, and stats payloads."""
        devices_by_id: dict[str, dict[str, Any]] = {}

        def upsert_device(
            payload: dict[str, Any],
            zone: dict[str, Any] | None = None,
            explicit_device_id: str | None = None,
        ) -> None:
            device_id = cls._resolve_device_id(explicit_device_id) or cls._device_id_from_payload(
                payload
            )
            if not device_id:
                return

            device_data = devices_by_id.setdefault(device_id, {})
            cls._merge_non_empty(device_data, payload)

            device_data.setdefault("id_device", device_id)
            device_data.setdefault("id", f"{smarthome_id}#{device_id}")

            if zone:
                for key in (
                    "zone_label",
                    "num_zone",
                    "label_zone_type",
                    "picto_zone_type",
                    "zone_img_id",
                ):
                    if zone.get(key) not in (None, "", []):
                        device_data[key] = zone[key]

        for device in details.get("devices", []):
            if isinstance(device, dict):
                upsert_device(device)

        for zone in details.get("zones", []):
            if not isinstance(zone, dict):
                continue
            for device in zone.get("devices", []):
                if isinstance(device, dict):
                    upsert_device(device, zone=zone)

        errors_by_device = (
            errors.get("results", {}).get("by_device", {}).get(smarthome_id, {})
            if isinstance(errors, dict)
            else {}
        )
        if isinstance(errors_by_device, dict):
            for device_id, error_payload in errors_by_device.items():
                if isinstance(error_payload, dict):
                    upsert_device(error_payload, explicit_device_id=str(device_id))

        stats_by_device = stats.get("devices", {}) if isinstance(stats, dict) else {}
        if isinstance(stats_by_device, dict):
            for device_id, stats_payload in stats_by_device.items():
                normalized_device_id = cls._resolve_device_id(device_id)
                if not normalized_device_id:
                    continue
                device_data = devices_by_id.setdefault(
                    normalized_device_id,
                    {
                        "id_device": normalized_device_id,
                        "id": f"{smarthome_id}#{normalized_device_id}",
                    },
                )
                if isinstance(stats_payload, dict):
                    device_data["stats"] = stats_payload

        for device_data in devices_by_id.values():
            if not isinstance(device_data.get("errors"), list):
                device_data["errors"] = []
            if not isinstance(device_data.get("stats"), dict):
                device_data["stats"] = {}

        ordered_device_ids = sorted(devices_by_id)
        devices = [devices_by_id[device_id] for device_id in ordered_device_ids]
        return devices, devices_by_id

    @property
    def smarthomes(self) -> list[dict[str, Any]]:
        """Return list of smarthomes."""
        return self._smarthomes

    def get_smarthome_data(self, smarthome_id: str) -> dict[str, Any] | None:
        """Get data for a specific smarthome."""
        if not self.data:
            return None
        return self.data.get("smarthomes", {}).get(smarthome_id)

    def get_smarthome_devices(self, smarthome_id: str) -> list[dict[str, Any]]:
        """Get all normalized devices for a specific smarthome."""
        smarthome_data = self.get_smarthome_data(smarthome_id)
        if not smarthome_data:
            return []
        devices = smarthome_data.get("devices", [])
        return devices if isinstance(devices, list) else []

    def get_device_data(self, smarthome_id: str, device_id: str) -> dict[str, Any] | None:
        """Get data for a specific device."""
        smarthome_data = self.get_smarthome_data(smarthome_id)
        if not smarthome_data:
            return None

        devices_by_id = smarthome_data.get("devices_by_id", {})
        if isinstance(devices_by_id, dict):
            normalized_device_id = self._resolve_device_id(device_id) or device_id
            device_data = devices_by_id.get(normalized_device_id)
            if isinstance(device_data, dict):
                return device_data

        for device in self.get_smarthome_devices(smarthome_id):
            candidate_id = self._resolve_device_id(
                device.get("id_device") or device.get("id")
            )
            if candidate_id == self._resolve_device_id(device_id):
                return device

        return None
