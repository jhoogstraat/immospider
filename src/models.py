from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Listing:
    id: str | None
    title: str | None
    url: str
    address: str | None
    price_eur: float | None
    living_area_m2: float | None
    rooms: float | None
    provider: str | None
    published: str | None
    source: str
    source_color: int
    image_url: str | None
    google_maps_url: str | None


@dataclass(frozen=True, slots=True)
class ListingSource:
    name: str
    host: str
    color: int
    extract: Callable[[str, str], list[Listing]]
