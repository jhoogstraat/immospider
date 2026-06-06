from __future__ import annotations
from typing import NotRequired, TypedDict, cast


from . import immobilienscout24, immowelt, kleinanzeigen

class FetchOptions(TypedDict):
    google_search: NotRequired[bool]
    solve_cloudflare: NotRequired[bool]


FETCH_OPTIONS_BY_HOST: dict[str, FetchOptions] = {
    immobilienscout24.HOST: cast(FetchOptions, cast(object, immobilienscout24.FETCH_OPTIONS)),
    immowelt.HOST: cast(FetchOptions, cast(object, immowelt.FETCH_OPTIONS)),
    kleinanzeigen.HOST: cast(FetchOptions, cast(object, kleinanzeigen.FETCH_OPTIONS)),
}


def fetch_options_for_url(url: str) -> FetchOptions:
    from urllib.parse import urlparse

    return FETCH_OPTIONS_BY_HOST.get(urlparse(url).netloc, {}).copy()


__all__ = [
    "FETCH_OPTIONS_BY_HOST",
    "FetchOptions",
    "fetch_options_for_url",
]
