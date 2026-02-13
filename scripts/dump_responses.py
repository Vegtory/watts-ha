#!/usr/bin/env python3
"""Dump reachable Watts SmartHome API responses to .responses/ (gitignored).

This script will:
 - load `.env` from the repo root
 - login and save token response
 - fetch user data and save
 - discover smarthome and device ids from user/smarthome data
 - call every known API endpoint and save each response
 - errors are saved alongside responses for inspection

It deliberately avoids destructive endpoints (like program apply).
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import time
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def load_dotenv(env_path: pathlib.Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, val = line.split('=', 1)
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


load_dotenv(REPO_ROOT / '.env')

import aiohttp  # noqa: E402

from custom_components.watts_smarthome.api import WattsApiClient  # noqa: E402
from custom_components.watts_smarthome.const import (  # noqa: E402
    API_BASE_URL,
    DEFAULT_LANG,
)

OUT_DIR = REPO_ROOT / '.responses'
RUN_TS = int(time.time())


def write_json(name: str, data: Any) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{RUN_TS}_{name}.json"
    with path.open('w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"  ✓ {path.name}")


async def safe_call(label: str, coro: Any) -> Any:
    """Await *coro*, write the result or error, and return it (or None)."""
    try:
        resp = await coro
        write_json(label, resp)
        return resp
    except Exception as exc:
        write_json(f'{label}_error', {'error': str(exc), 'type': type(exc).__name__})
        print(f"  ✗ {label}: {exc}")
        return None


def extract_smarthome_ids(user_data: dict) -> list[str]:
    """Extract smarthome IDs from user/read response."""
    ids: list[str] = []
    for sh in user_data.get('data', {}).get('smarthomes', []):
        sid = sh.get('smarthome_id')
        if sid:
            ids.append(sid)
    return ids


def extract_device_ids(smarthome_data: dict) -> list[str]:
    """Extract device IDs from smarthome/read response."""
    ids: list[str] = []
    for dev in smarthome_data.get('data', {}).get('devices', []):
        did = dev.get('id')
        if did:
            ids.append(did)
    return ids


async def main() -> int:
    username = os.environ.get('WATTS_USERNAME')
    password = os.environ.get('WATTS_PASSWORD')

    if not username or not password:
        print("WATTS_USERNAME and WATTS_PASSWORD must be set in .env or environment.", file=sys.stderr)
        return 2

    client = WattsApiClient(username, password)

    try:
        # ------------------------------------------------------------------
        # 1. Login  (POST /realms/watts/protocol/openid-connect/token)
        # ------------------------------------------------------------------
        print("\n── Login ──")
        try:
            token = await client.async_login()
            write_json('token', token)
        except Exception as exc:
            write_json('token_error', {'error': str(exc)})
            print("Login failed:", exc)
            return 3

        # ------------------------------------------------------------------
        # 2. User read  (POST /api/v0.1/human/user/read/)
        # ------------------------------------------------------------------
        print("\n── User read ──")
        user = await safe_call('user_read', client.async_get_user_data())
        if user is None:
            print("Cannot continue without user data.")
            return 4

        smarthome_ids = extract_smarthome_ids(user)
        print(f"\nDiscovered smarthome_ids: {smarthome_ids}")

        # ------------------------------------------------------------------
        # 3. Extra user/sandbox endpoints not wrapped in API client
        #    These use the low-level _request helper.
        # ------------------------------------------------------------------
        print("\n── User / sandbox extras ──")

        # POST /api/v0.1/human/user/get_lang/
        await safe_call(
            'user_get_lang',
            client._request('POST', '/api/v0.1/human/user/get_lang/', data={'lang': DEFAULT_LANG}),
        )

        # POST /api/v0.1/human/sandbox/get_current_timestamp/
        await safe_call(
            'sandbox_get_current_timestamp',
            client._request('POST', '/api/v0.1/human/sandbox/get_current_timestamp/', data={'lang': DEFAULT_LANG, '0': ''}),
        )

        # POST /api/v0.1/human/sandbox/get_db_version/
        await safe_call(
            'sandbox_get_db_version',
            client._request('POST', '/api/v0.1/human/sandbox/get_db_version/', data={'lang': DEFAULT_LANG}),
        )

        # POST /api/v0.1/human/sandbox/get_last_cgu/
        await safe_call(
            'sandbox_get_last_cgu',
            client._request('POST', '/api/v0.1/human/sandbox/get_last_cgu/', data={'lang': DEFAULT_LANG}),
        )

        # POST /api/v0.1/human/mobile/read_demo/
        await safe_call(
            'mobile_read_demo',
            client._request('POST', '/api/v0.1/human/mobile/read_demo/', data={'lang': DEFAULT_LANG}),
        )

        # ------------------------------------------------------------------
        # 4. Per-smarthome endpoints
        # ------------------------------------------------------------------
        for sid in smarthome_ids:
            safe_sid = sid.replace('#', '_')
            print(f"\n── Smarthome {sid} ──")

            # POST /api/v0.1/human/smarthome/read/
            sh_data = await safe_call(
                f'smarthome_{safe_sid}_read',
                client.async_get_smarthome_data(sid),
            )

            # POST /api/v0.1/human/smarthome/get_errors/
            await safe_call(
                f'smarthome_{safe_sid}_get_errors',
                client.async_get_errors(sid),
            )

            # POST /api/v0.1/human/sandbox/check_last_connexion/
            await safe_call(
                f'smarthome_{safe_sid}_check_last_connexion',
                client.async_check_last_connection(sid),
            )

            # POST /api/v0.1/human/smarthome/time_offset/
            await safe_call(
                f'smarthome_{safe_sid}_time_offset',
                client.async_get_time_offset(sid),
            )

            # POST /api/v0.1/human/query/check_failure/
            await safe_call(
                f'smarthome_{safe_sid}_query_check_failure',
                client._request(
                    'POST',
                    '/api/v0.1/human/query/check_failure/',
                    data={'smarthome_id': sid, 'lang': DEFAULT_LANG},
                ),
            )

            # POST /api/v0.1/human/stats/read/
            await safe_call(
                f'smarthome_{safe_sid}_stats_read',
                client._request(
                    'POST',
                    '/api/v0.1/human/stats/read/',
                    data={'smarthome_id': sid, 'lang': DEFAULT_LANG},
                ),
            )

            # ----------------------------------------------------------
            # 5. Per-device endpoints (discovered from smarthome/read)
            # ----------------------------------------------------------
            device_ids = extract_device_ids(sh_data) if sh_data else []
            print(f"  Devices: {device_ids}")

            for did in device_ids:
                safe_did = did.replace('#', '_')

                # POST /api/v0.1/human/sandbox/convert_program/
                await safe_call(
                    f'device_{safe_did}_convert_program',
                    client.async_convert_program(
                        {'device_id': did, 'now': str(int(time.time()))},
                    ),
                )

        # ------------------------------------------------------------------
        # 6. GET endpoints (no form body required)
        # ------------------------------------------------------------------
        print("\n── GET endpoints ──")

        # GET /api/v0.1/human/smarthome/user_manual/
        session = await client._ensure_session()
        try:
            async with session.get(
                f'{API_BASE_URL}/api/v0.1/human/smarthome/user_manual/',
                headers={'Authorization': f'Bearer {client._access_token}'},
            ) as resp:
                ct = resp.headers.get('Content-Type', '')
                if 'json' in ct:
                    body = await resp.json()
                else:
                    body = {'status': resp.status, 'content_type': ct, 'body_preview': (await resp.text())[:500]}
                write_json('smarthome_user_manual', body)
        except Exception as exc:
            write_json('smarthome_user_manual_error', {'error': str(exc)})

    finally:
        await client.close()

    print(f"\nDone – all responses saved in {OUT_DIR}/")
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
