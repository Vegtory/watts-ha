#!/usr/bin/env python3
"""Helper to test Watts SmartHome API locally using .env.

Usage:
  python scripts/test_api.py

It will load `.env` from the repo root (if present), perform a login,
print the token response, and attempt to fetch basic user data.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

# Ensure repo root is importable
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def load_dotenv(env_path: pathlib.Path) -> None:
    """Load simple KEY=VALUE pairs from a .env file into os.environ if not set."""
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

from custom_components.watts_smarthome.api import WattsApiClient


async def main() -> int:
    username = os.environ.get('WATTS_USERNAME')
    password = os.environ.get('WATTS_PASSWORD')

    if not username or not password:
        print("WATTS_USERNAME and WATTS_PASSWORD must be set in .env or environment.", file=sys.stderr)
        return 2

    client = WattsApiClient(username, password)
    try:
        print("Logging in...")
        token = await client.async_login()
        print("\nTOKEN RESPONSE:\n")
        print(json.dumps(token, indent=2))

        try:
            user = await client.async_get_user_data()
            print("\nUSER DATA:\n")
            print(json.dumps(user, indent=2))
        except Exception as exc:  # pragma: no cover - runtime helper
            print("\nFailed to fetch user data:", exc, file=sys.stderr)

    finally:
        await client.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
