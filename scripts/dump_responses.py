#!/usr/bin/env python3
"""Dump responses for all operations defined in watts-openapi.yaml.

The script:
 - loads `.env`
 - logs in
 - executes every `method + path` present in `watts-openapi.yaml`
 - runs per-smarthome calls for every discovered smarthome
 - runs `query/push` for every discovered device in every smarthome
 - saves responses (and errors) into `.responses/` with one file per call
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import sys
import time
from collections.abc import Mapping
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

OPENAPI_PATH = REPO_ROOT / "watts-openapi.yaml"
OUT_DIR = REPO_ROOT / ".responses"
RUN_TS = int(time.time())

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
_QUERY_COPY_FIELDS = (
    "gv_mode",
    "nv_mode",
    "time_boost",
    "consigne_boost",
    "consigne_manuel",
    "consigne_confort",
    "consigne_eco",
    "consigne_hg",
)


def load_dotenv(env_path: pathlib.Path) -> None:
    """Populate environment from .env if present."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv(REPO_ROOT / ".env")

import aiohttp  # noqa: E402
import yaml  # noqa: E402

from custom_components.watts_smarthome.api import WattsApiClient, WattsApiError  # noqa: E402
from custom_components.watts_smarthome.const import AUTH_BASE_URL, DEFAULT_LANG  # noqa: E402


def slug(value: str) -> str:
    """Create filesystem-safe suffix."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return safe or "value"


def write_json(name: str, payload: Any) -> None:
    """Write payload as pretty JSON under .responses."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{RUN_TS}_{name}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(f"  ✓ {path.name}")


def load_spec_operations() -> set[str]:
    """Return all operations from watts-openapi.yaml as `METHOD /path`."""
    with OPENAPI_PATH.open("r", encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    operations: set[str] = set()
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, Mapping):
            continue
        for method in path_item:
            if method.lower() in _HTTP_METHODS:
                operations.add(f"{method.upper()} {path}")
    return operations


def extract_smarthome_ids(user_payload: Mapping[str, Any]) -> list[str]:
    """Extract unique smarthome ids from user/read payload."""
    ids: set[str] = set()
    data = user_payload.get("data", {})
    if not isinstance(data, Mapping):
        return []
    smarthomes = data.get("smarthomes", [])
    if not isinstance(smarthomes, list):
        return []
    for item in smarthomes:
        if not isinstance(item, Mapping):
            continue
        sid = str(item.get("smarthome_id", "")).strip()
        if sid:
            ids.add(sid)
    return sorted(ids)


def extract_devices(smarthome_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract devices indexed by short device id from smarthome/read payload."""
    result: dict[str, dict[str, Any]] = {}
    data = smarthome_payload.get("data", {})
    if not isinstance(data, Mapping):
        return result

    def add_device(raw: Any) -> None:
        if not isinstance(raw, Mapping):
            return
        did = str(raw.get("id_device", "")).strip()
        if not did:
            full_id = str(raw.get("id", "")).strip()
            if "#" in full_id:
                did = full_id.split("#", 1)[1]
            else:
                did = full_id
        if did:
            result[did] = dict(raw)

    devices = data.get("devices", [])
    if isinstance(devices, list):
        for raw_device in devices:
            add_device(raw_device)

    zones = data.get("zones", [])
    if isinstance(zones, list):
        for zone in zones:
            if not isinstance(zone, Mapping):
                continue
            zone_devices = zone.get("devices", [])
            if not isinstance(zone_devices, list):
                continue
            for raw_device in zone_devices:
                add_device(raw_device)

    return result


def build_noop_query(device_id: str, device: Mapping[str, Any]) -> dict[str, str]:
    """Build a query/push payload that re-sends current values for a device."""
    query: dict[str, str] = {"id_device": device_id}
    for field in _QUERY_COPY_FIELDS:
        value = device.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        query[field] = text

    if "gv_mode" in query and "nv_mode" not in query:
        query["nv_mode"] = query["gv_mode"]
    if "nv_mode" in query and "gv_mode" not in query:
        query["gv_mode"] = query["nv_mode"]

    if "consigne_manuel" not in query:
        for fallback in ("consigne_boost", "consigne_confort", "consigne_eco", "consigne_hg"):
            if fallback in query:
                query["consigne_manuel"] = query[fallback]
                break

    return query


async def safe_call(
    *,
    label: str,
    operation: str,
    coro: Any,
    attempted_ops: set[str],
    successful_ops: set[str],
) -> Any:
    """Await a coroutine and persist either its result or an error file."""
    attempted_ops.add(operation)
    try:
        response = await coro
        write_json(label, response)
        successful_ops.add(operation)
        return response
    except Exception as err:
        write_json(f"{label}_error", {"error": str(err), "type": type(err).__name__})
        print(f"  ✗ {label}: {err}")
        return None


async def async_get_account(client: WattsApiClient) -> dict[str, Any]:
    """Call GET /realms/watts/account against auth server."""
    await client._ensure_access_token()
    if client._access_token is None:
        raise WattsApiError("No access token available")

    headers = {"Authorization": f"Bearer {client._access_token}"}
    status, payload = await client._async_raw_request(
        "GET",
        f"{AUTH_BASE_URL}/realms/watts/account",
        headers=headers,
    )
    if status in (401, 403):
        await client._force_reauthenticate()
        if client._access_token is None:
            raise WattsApiError("No access token available after re-auth")
        headers = {"Authorization": f"Bearer {client._access_token}"}
        status, payload = await client._async_raw_request(
            "GET",
            f"{AUTH_BASE_URL}/realms/watts/account",
            headers=headers,
        )
    if status >= 400:
        raise WattsApiError(f"Watts account endpoint returned HTTP {status}")
    return payload


async def main() -> int:
    username = os.environ.get("WATTS_USERNAME")
    password = os.environ.get("WATTS_PASSWORD")

    if not username or not password:
        print("WATTS_USERNAME and WATTS_PASSWORD must be set in .env or environment.", file=sys.stderr)
        return 2

    spec_operations = load_spec_operations()
    attempted_ops: set[str] = set()
    successful_ops: set[str] = set()

    async with aiohttp.ClientSession() as session:
        client = WattsApiClient(session=session, username=username, password=password)

        print("\n── Token / Account ──")
        token = await safe_call(
            label="token",
            operation="POST /realms/watts/protocol/openid-connect/token",
            coro=client.async_login(),
            attempted_ops=attempted_ops,
            successful_ops=successful_ops,
        )
        if token is None:
            print("Login failed, cannot continue.")
            return 3

        await safe_call(
            label="account_read",
            operation="GET /realms/watts/account",
            coro=async_get_account(client),
            attempted_ops=attempted_ops,
            successful_ops=successful_ops,
        )

        print("\n── User-level Calls ──")
        user_payload = await safe_call(
            label="user_read",
            operation="POST /api/v0.1/human/user/read/",
            coro=client.async_get_user_data(),
            attempted_ops=attempted_ops,
            successful_ops=successful_ops,
        )
        if not isinstance(user_payload, Mapping):
            print("Cannot continue without user/read response.")
            return 4

        await safe_call(
            label="user_get_lang",
            operation="POST /api/v0.1/human/user/get_lang/",
            coro=client._request("POST", "/api/v0.1/human/user/get_lang/", data={"lang": DEFAULT_LANG}),
            attempted_ops=attempted_ops,
            successful_ops=successful_ops,
        )
        await safe_call(
            label="sandbox_get_current_timestamp",
            operation="POST /api/v0.1/human/sandbox/get_current_timestamp/",
            coro=client._request(
                "POST",
                "/api/v0.1/human/sandbox/get_current_timestamp/",
                data={"lang": DEFAULT_LANG, "0": "0"},
            ),
            attempted_ops=attempted_ops,
            successful_ops=successful_ops,
        )
        await safe_call(
            label="sandbox_get_db_version",
            operation="POST /api/v0.1/human/sandbox/get_db_version/",
            coro=client._request(
                "POST",
                "/api/v0.1/human/sandbox/get_db_version/",
                data={"lang": DEFAULT_LANG, "0": "0"},
            ),
            attempted_ops=attempted_ops,
            successful_ops=successful_ops,
        )

        smarthome_ids = extract_smarthome_ids(user_payload)
        print(f"\nDiscovered smarthomes: {smarthome_ids}")

        for smarthome_id in smarthome_ids:
            safe_sid = slug(smarthome_id)
            print(f"\n── Smarthome {smarthome_id} ──")

            smarthome_payload = await safe_call(
                label=f"smarthome_{safe_sid}_read",
                operation="POST /api/v0.1/human/smarthome/read/",
                coro=client.async_get_smarthome_data(smarthome_id),
                attempted_ops=attempted_ops,
                successful_ops=successful_ops,
            )
            await safe_call(
                label=f"smarthome_{safe_sid}_get_errors",
                operation="POST /api/v0.1/human/smarthome/get_errors/",
                coro=client.async_get_errors(smarthome_id),
                attempted_ops=attempted_ops,
                successful_ops=successful_ops,
            )
            await safe_call(
                label=f"smarthome_{safe_sid}_check_last_connexion",
                operation="POST /api/v0.1/human/sandbox/check_last_connexion/",
                coro=client.async_check_last_connection(smarthome_id),
                attempted_ops=attempted_ops,
                successful_ops=successful_ops,
            )
            await safe_call(
                label=f"smarthome_{safe_sid}_time_offset",
                operation="POST /api/v0.1/human/smarthome/time_offset/",
                coro=client.async_get_time_offset(smarthome_id),
                attempted_ops=attempted_ops,
                successful_ops=successful_ops,
            )
            await safe_call(
                label=f"smarthome_{safe_sid}_query_check_failure",
                operation="POST /api/v0.1/human/query/check_failure/",
                coro=client.async_check_query_failure(smarthome_id),
                attempted_ops=attempted_ops,
                successful_ops=successful_ops,
            )

            devices = (
                extract_devices(smarthome_payload)
                if isinstance(smarthome_payload, Mapping)
                else {}
            )
            print(f"  Devices: {sorted(devices)}")
            for device_id, device in sorted(devices.items()):
                safe_did = slug(device_id)
                query = build_noop_query(device_id, device)
                await safe_call(
                    label=f"smarthome_{safe_sid}_device_{safe_did}_query_push",
                    operation="POST /api/v0.1/human/query/push/",
                    coro=client.async_push_query(smarthome_id, query),
                    attempted_ops=attempted_ops,
                    successful_ops=successful_ops,
                )

    missing_ops = sorted(spec_operations - attempted_ops)
    summary = {
        "operations_in_spec": sorted(spec_operations),
        "operations_attempted": sorted(attempted_ops),
        "operations_successful": sorted(successful_ops),
        "operations_missing": missing_ops,
        "smarthomes_count": len(smarthome_ids),
    }
    write_json("summary", summary)

    if missing_ops:
        print("\nMissing operations:")
        for operation in missing_ops:
            print(f"  - {operation}")
        print(f"\nDone with gaps. Responses saved in {OUT_DIR}/")
        return 5

    print(f"\nDone – all operations attempted. Responses saved in {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
