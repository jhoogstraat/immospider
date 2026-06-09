from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin, urlparse

from scrapling.parser import Selector

from models import Listing, ListingSource
from .common import dedupe

SOURCE_NAME = "Kleinanzeigen"
SOURCE_COLOR = 0x86B817
HOST = "www.kleinanzeigen.de"

_ID_RE = re.compile(r"/s-anzeige/[^/]+/(?P<id>\d+)-\d+-\d+")
_SIZE_RE = re.compile(r"(?P<value>[\d.]+(?:,\d+)?)\s*(?:m²|qm)", re.IGNORECASE)
_ROOMS_RE = re.compile(r"(?P<value>\d+(?:,\d+)?)\s*Zi\.", re.IGNORECASE)
_PRICE_VALUE_RE = re.compile(r"(?P<value>[\d.]+(?:,\d+)?)\s*€")
_SPACE_RE = re.compile(r"\s+")

SOURCE = ListingSource(
    name=SOURCE_NAME,
    host=HOST,
    color=SOURCE_COLOR,
    extract=lambda html, base_url: extract_listings(html, base_url),
)


def extract_listings(html: str, base_url: str = "https://www.kleinanzeigen.de") -> list[Listing]:
    page = Selector(html)
    listings: list[Listing] = []
    for article in page.css("article.aditem"):
        listing = _listing_from_article(article, base_url)
        if listing is not None:
            listings.append(listing)
    return dedupe(listings)


def _listing_from_article(article: Selector, base_url: str) -> Listing | None:
    href = _attr(article, "data-href") or _css_text(article, 'a[href*="/s-anzeige/"]::attr(href)')
    if href is None:
        return None
    url = urljoin(base_url, href)
    if urlparse(url).netloc != HOST:
        return None

    listing_id = _attr(article, "data-adid") or _id_from_url(url)
    address = _css_all_text(article, ".aditem-main--top--left")
    tags = _css_all_text(article, ".aditem-main--middle--tags") or ""
    return Listing(
        id=listing_id,
        title=_css_text(article, "h2 a::text") or _css_text(article, "h2::text"),
        url=url,
        address=address,
        price_eur=_number_from_regex(_PRICE_VALUE_RE, _css_all_text(article, ".aditem-main--middle--price-shipping--price") or ""),
        price_label=None,
        utilities_eur=None,
        living_area_m2=_number_from_regex(_SIZE_RE, tags),
        rooms=_number_from_regex(_ROOMS_RE, tags),
        provider=_css_text(article, ".simpletag::text"),
        published=_css_all_text(article, ".aditem-main--top--right"),
        source=SOURCE_NAME,
        source_color=SOURCE_COLOR,
        image_url=_image_url(article, base_url),
        google_maps_url=_google_maps_url(address),
    )


def _css_text(element: Selector, css_selector: str) -> str | None:
    value = element.css(css_selector).get()
    return _clean(str(value)) if value is not None else None

def _css_all_text(element: Selector, css_selector: str) -> str | None:
    match = element.css(css_selector)
    if not match:
        return None
    return _clean(str(match[0].get_all_text(ignore_tags=("script", "style")) or ""))


def _attr(element: Selector, name: str) -> str | None:
    value = element.attrib.get(name)
    return _clean(str(value)) if value is not None else None


def _image_url(article: Selector, base_url: str) -> str | None:
    src = _css_text(article, "img::attr(src)") or _css_text(article, "img::attr(data-src)")
    return urljoin(base_url, src) if src is not None else None


def _id_from_url(url: str) -> str | None:
    match = _ID_RE.search(urlparse(url).path)
    return match.group("id") if match is not None else None


def _google_maps_url(address: str | None) -> str | None:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(address)}" if address is not None else None


def _number_from_regex(pattern: re.Pattern[str], text: str) -> float | None:
    match = pattern.search(text)
    return _to_float(match.group("value")) if match is not None else None


def _to_float(value: str) -> float | None:
    normalized = re.sub(r"[^0-9.-]", "", value.strip().replace(".", "").replace(",", "."))
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _clean(value: str) -> str | None:
    cleaned = _SPACE_RE.sub(" ", value).strip()
    return cleaned or None
