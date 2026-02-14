"""Coordinator for Watts SmartHome data."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WattsApiClient, WattsApiError, WattsAuthError, WattsConnectionError

_LOGGER = logging.getLogger(__name__)

_BASE_QUERY_KEYS: tuple[str, ...] = (
    "id_device",
    "gv_mode",
    "nv_mode",
    "time_boost",
    "consigne_confort",
    "consigne_eco",
    "consigne_hg",
    "consigne_boost",
    "consigne_manuel",
)


class WattsDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Handle fetching Watts SmartHome data."""

    api: WattsApiClient

    def __init__(
        self,
        hass: HomeAssistant,
        api: WattsApiClient,
        *,
        update_interval_seconds: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Watts SmartHome",
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.api = api
        self._command_lock = asyncio.Lock()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            user_payload = await self.api.async_get_user_data()
            user_data = user_payload.get("data", {})
            smarthomes: dict[str, dict[str, Any]] = {}

            for smarthome in user_data.get("smarthomes", []):
                if not isinstance(smarthome, Mapping):
                    continue

                smarthome_id = str(smarthome.get("smarthome_id", "")).strip()
                if not smarthome_id:
                    continue

                smarthome_payload = await self.api.async_get_smarthome_data(smarthome_id)
                smarthome_data = smarthome_payload.get("data", {})
                devices = self._extract_devices(smarthome_id, smarthome_data)

                smarthomes[smarthome_id] = {
                    "meta": dict(smarthome),
                    "state": smarthome_data,
                    "devices": devices,
                }

            return {
                "user": user_data,
                "smarthomes": smarthomes,
            }
        except WattsAuthError as err:
            raise ConfigEntryAuthFailed from err
        except WattsConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except WattsApiError as err:
            raise UpdateFailed(str(err)) from err

    def _extract_devices(
        self,
        smarthome_id: str,
        smarthome_data: Mapping[str, Any],
    ) -> dict[str, dict[str, Any]]:
        devices: dict[str, dict[str, Any]] = {}

        raw_devices = smarthome_data.get("devices", [])
        if isinstance(raw_devices, list):
            for raw_device in raw_devices:
                if not isinstance(raw_device, Mapping):
                    continue
                normalized = self._normalize_device(smarthome_id, raw_device)
                if normalized is None:
                    continue
                devices[normalized["id_device"]] = normalized

        zones = smarthome_data.get("zones", [])
        if isinstance(zones, list):
            for zone in zones:
                if not isinstance(zone, Mapping):
                    continue
                zone_label = zone.get("zone_label")
                zone_devices = zone.get("devices", [])
                if not isinstance(zone_devices, list):
                    continue
                for raw_device in zone_devices:
                    if not isinstance(raw_device, Mapping):
                        continue
                    normalized = self._normalize_device(
                        smarthome_id,
                        raw_device,
                        zone_label=str(zone_label) if zone_label else None,
                    )
                    if normalized is None:
                        continue
                    device_id = normalized["id_device"]
                    if device_id in devices:
                        if normalized.get("zone_label") and not devices[device_id].get("zone_label"):
                            devices[device_id]["zone_label"] = normalized["zone_label"]
                    else:
                        devices[device_id] = normalized

        return devices

    def _normalize_device(
        self,
        smarthome_id: str,
        raw_device: Mapping[str, Any],
        zone_label: str | None = None,
    ) -> dict[str, Any] | None:
        device = dict(raw_device)
        device_id = str(device.get("id_device", "")).strip()
        if not device_id:
            full_id = str(device.get("id", "")).strip()
            if "#" in full_id:
                device_id = full_id.split("#", 1)[1]
            else:
                device_id = full_id
        if not device_id:
            return None

        device["id_device"] = device_id
        device.setdefault("id", f"{smarthome_id}#{device_id}")
        device["smarthome_id"] = smarthome_id
        if zone_label:
            device["zone_label"] = zone_label
        return device

    def iter_device_keys(self) -> list[tuple[str, str]]:
        """Return all known (smarthome_id, device_id) pairs."""
        result: list[tuple[str, str]] = []
        for smarthome_id, smarthome_data in self.data.get("smarthomes", {}).items():
            for device_id in smarthome_data.get("devices", {}):
                result.append((smarthome_id, device_id))
        return result

    def get_device(self, smarthome_id: str, device_id: str) -> dict[str, Any] | None:
        """Return a single device payload."""
        smarthome = self.data.get("smarthomes", {}).get(smarthome_id, {})
        return smarthome.get("devices", {}).get(device_id)

    def get_smarthome_label(self, smarthome_id: str) -> str:
        """Return friendly label for a smarthome."""
        smarthome = self.data.get("smarthomes", {}).get(smarthome_id, {})
        meta = smarthome.get("meta", {})
        state = smarthome.get("state", {})
        return str(meta.get("label") or state.get("label") or smarthome_id)

    def get_device_name(self, smarthome_id: str, device_id: str) -> str:
        """Return friendly label for a device."""
        device = self.get_device(smarthome_id, device_id)
        if not device:
            return device_id
        label_interface = str(device.get("label_interface") or "").strip()
        if label_interface:
            return label_interface
        name = str(device.get("nom_appareil") or "").strip()
        if name:
            return name
        zone_label = str(device.get("zone_label") or "").strip()
        if zone_label:
            return zone_label
        return device_id

    def _base_query(self, device_id: str, device: Mapping[str, Any]) -> dict[str, str]:
        query: dict[str, str] = {"id_device": device_id}
        for key in _BASE_QUERY_KEYS:
            if key == "id_device":
                continue
            value = device.get(key)
            if value is None:
                continue
            query[key] = str(value)
        return query

    async def async_push_device_update(
        self,
        smarthome_id: str,
        device_id: str,
        updates: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Push an update for a single device and refresh coordinator data."""
        diagnostic: dict[str, Any] = {"attempts": []}

        async with self._command_lock:
            device = self.get_device(smarthome_id, device_id)
            if device is None:
                raise HomeAssistantError(f"Unknown Watts device: {smarthome_id}#{device_id}")

            query: dict[str, str] = {"id_device": device_id}
            for key, value in updates.items():
                query[key] = str(value)

            try:
                response = await self.api.async_push_query(smarthome_id, query)
                diagnostic["attempts"].append(
                    {
                        "strategy": "minimal",
                        "query": dict(query),
                        "code": self._response_code(response),
                        "key": self._response_key(response),
                        "value": self._response_value(response),
                    }
                )
            except WattsApiError as err:
                diagnostic["attempts"].append(
                    {
                        "strategy": "minimal",
                        "query": dict(query),
                        "error": str(err),
                    }
                )
                # Fallback with full snapshot payload for backend variants that require full context.
                fallback_query = self._base_query(device_id, device)
                fallback_query.update(query)
                try:
                    response = await self.api.async_push_query(smarthome_id, fallback_query)
                    diagnostic["attempts"].append(
                        {
                            "strategy": "fallback_full",
                            "query": dict(fallback_query),
                            "code": self._response_code(response),
                            "key": self._response_key(response),
                            "value": self._response_value(response),
                        }
                    )
                except WattsApiError as fallback_err:
                    diagnostic["attempts"].append(
                        {
                            "strategy": "fallback_full",
                            "query": dict(fallback_query),
                            "error": str(fallback_err),
                        }
                    )
                    raise HomeAssistantError(
                        f"Failed to update Watts device: {fallback_err}"
                    ) from fallback_err

        await self.async_request_refresh()
        return diagnostic

    async def async_check_query_failure(self, smarthome_id: str) -> dict[str, Any]:
        """Return query failure payload for diagnostics."""
        try:
            return await self.api.async_check_query_failure(smarthome_id)
        except WattsApiError as err:
            return {"error": str(err)}

    @staticmethod
    def _response_code(response: Mapping[str, Any]) -> str | None:
        code = response.get("code")
        if isinstance(code, Mapping):
            return str(code.get("code"))
        return None

    @staticmethod
    def _response_key(response: Mapping[str, Any]) -> str | None:
        code = response.get("code")
        if isinstance(code, Mapping):
            value = code.get("key")
            return str(value) if value is not None else None
        return None

    @staticmethod
    def _response_value(response: Mapping[str, Any]) -> str | None:
        code = response.get("code")
        if isinstance(code, Mapping):
            value = code.get("value")
            return str(value) if value is not None else None
        return None
