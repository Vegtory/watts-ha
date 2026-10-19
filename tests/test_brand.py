"""The repository-root brand/ folder (for HACS) must match the integration's brand/ folder."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("icon.png", "icon@2x.png", "dark_icon.png", "dark_icon@2x.png")


def test_root_brand_matches_integration() -> None:
    for name in FILES:
        integration = (ROOT / "custom_components" / "watts_smarthome" / "brand" / name).read_bytes()
        root = (ROOT / "brand" / name).read_bytes()
        assert root == integration, f"brand/{name} differs; copy it from custom_components/watts_smarthome/brand/"
