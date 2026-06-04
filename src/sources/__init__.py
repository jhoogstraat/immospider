from __future__ import annotations

from urllib.parse import urlparse

from models import ListingSource

from . import immobilienscout24, immowelt

DEFAULT_SOURCES = (immobilienscout24.SOURCE, immowelt.SOURCE)


def source_for_url(url: str, sources: tuple[ListingSource, ...] = DEFAULT_SOURCES) -> ListingSource:
    host = urlparse(url).netloc
    for source in sources:
        if host == source.host:
            return source
    raise ValueError(f"unsupported listing source host: {host or url}")


__all__ = ["DEFAULT_SOURCES", "source_for_url"]
