from __future__ import annotations

from . import immobilienscout24, immowelt

IMMOBILIENSCOUT24_URL = immobilienscout24.URL
IMMOWELT_URL = immowelt.URL
DEFAULT_URL = IMMOBILIENSCOUT24_URL
DEFAULT_URLS = (IMMOBILIENSCOUT24_URL, IMMOWELT_URL)

__all__ = [
    "DEFAULT_URL",
    "DEFAULT_URLS",
    "IMMOBILIENSCOUT24_URL",
    "IMMOWELT_URL",
]
