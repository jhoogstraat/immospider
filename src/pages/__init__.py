from __future__ import annotations

from . import immobilienscout24, immowelt, kleinanzeigen

FETCH_OPTIONS_BY_HOST = {
    immobilienscout24.HOST: immobilienscout24.FETCH_OPTIONS,
    immowelt.HOST: immowelt.FETCH_OPTIONS,
    kleinanzeigen.HOST: kleinanzeigen.FETCH_OPTIONS,
}


def fetch_options_for_url(url: str) -> dict[str, object]:
    from urllib.parse import urlparse

    return dict(FETCH_OPTIONS_BY_HOST.get(urlparse(url).netloc, {}))


__all__ = [
    "FETCH_OPTIONS_BY_HOST",
    "fetch_options_for_url",
]
