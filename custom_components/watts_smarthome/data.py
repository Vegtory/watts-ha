"""Runtime data structures for Watts SmartHome integration."""

from __future__ import annotations

from dataclasses import dataclass

from .api import WattsApiClient
from .coordinator import WattsDataUpdateCoordinator


@dataclass(slots=True)
class WattsRuntimeData:
    """Objects stored per config entry."""

    client: WattsApiClient
    coordinator: WattsDataUpdateCoordinator
