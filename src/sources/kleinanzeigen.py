from __future__ import annotations

import re
from html import unescape
from urllib.parse import quote_plus, urljoin, urlparse

from models import Listing, ListingSource
from .common import dedupe

SOURCE_NAME = "Kleinanzeigen"
SOURCE_COLOR = 0x86B817
HOST = "www.kleinanzeigen.de"

_ARTICLE_RE = re.compile(r'<article\b[^>]*class=["\'][^"\']*\baditem\b[^"\']*["\'][^>]*>.*?</article>', re.IGNORECASE | re.DOTALL)
_DATA_ADID_RE = re.compile(r'\bdata-adid=["\'](?P<id>\d+)["\']', re.IGNORECASE)
_DATA_HREF_RE = re.compile(r'\bdata-href=["\'](?P<href>/s-anzeige/[^"\']+)["\']', re.IGNORECASE)
_LINK_RE = re.compile(r'href=["\'](?P<href>/s-anzeige/[^"\']+)["\']', re.IGNORECASE)
_ID_RE = re.compile(r"/s-anzeige/[^/]+/(?P<id>\d+)-\d+-\d+")
_TITLE_RE = re.compile(r'<h2\b[^>]*>.*?<a\b[^>]*>(?P<title>.*?)</a>.*?</h2>', re.IGNORECASE | re.DOTALL)
_TOP_LEFT_RE = re.compile(r'<div\b[^>]*class=["\'][^"\']*\baditem-main--top--left\b[^"\']*["\'][^>]*>(?P<value>.*?)</div>', re.IGNORECASE | re.DOTALL)
_TOP_RIGHT_RE = re.compile(r'<div\b[^>]*class=["\'][^"\']*\baditem-main--top--right\b[^"\']*["\'][^>]*>(?P<value>.*?)</div>', re.IGNORECASE | re.DOTALL)
_TAGS_RE = re.compile(r'<p\b[^>]*class=["\'][^"\']*\baditem-main--middle--tags\b[^"\']*["\'][^>]*>(?P<value>.*?)</p>', re.IGNORECASE | re.DOTALL)
_PRICE_RE = re.compile(r'<p\b[^>]*class=["\'][^"\']*\baditem-main--middle--price-shipping--price\b[^"\']*["\'][^>]*>(?P<value>.*?)</p>', re.IGNORECASE | re.DOTALL)
_PROVIDER_RE = re.compile(r'<span\b[^>]*class=["\'][^"\']*\bsimpletag\b[^"\']*["\'][^>]*>(?P<value>.*?)</span>', re.IGNORECASE | re.DOTALL)
_IMAGE_RE = re.compile(r'<img\b[^>]*(?:src|data-src)=["\'](?P<src>[^"\']+)["\']', re.IGNORECASE)
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
    listings: list[Listing] = []
    for match in _ARTICLE_RE.finditer(html):
        listing = _listing_from_article(match.group(0), base_url)
        if listing is not None:
            listings.append(listing)
    return dedupe(listings)


def _listing_from_article(article: str, base_url: str) -> Listing | None:
    href = _first_match(article, _DATA_HREF_RE, "href") or _first_match(article, _LINK_RE, "href")
    if href is None:
        return None
    url = urljoin(base_url, unescape(href))
    if urlparse(url).netloc != HOST:
        return None
    listing_id = _first_match(article, _DATA_ADID_RE, "id") or _id_from_url(url)
    address = _html_match_text(article, _TOP_LEFT_RE)
    return Listing(
        id=listing_id,
        title=_html_match_text(article, _TITLE_RE, "title"),
        url=url,
        address=address,
        price_eur=_number_from_regex(_PRICE_VALUE_RE, _html_match_text(article, _PRICE_RE) or ""),
        living_area_m2=_number_from_regex(_SIZE_RE, _html_match_text(article, _TAGS_RE) or ""),
        rooms=_number_from_regex(_ROOMS_RE, _html_match_text(article, _TAGS_RE) or ""),
        provider=_html_match_text(article, _PROVIDER_RE),
        published=_html_match_text(article, _TOP_RIGHT_RE),
        source=SOURCE_NAME,
        source_color=SOURCE_COLOR,
        image_url=_image_url(article, base_url),
        google_maps_url=_google_maps_url(address),
    )


def _first_match(text: str, pattern: re.Pattern[str], group: str) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    value = unescape(match.group(group)).strip()
    return value or None


def _html_match_text(text: str, pattern: re.Pattern[str], group: str = "value") -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    return _clean(_strip_tags(match.group(group)))


def _image_url(article: str, base_url: str) -> str | None:
    match = _IMAGE_RE.search(article)
    if match is None:
        return None
    return urljoin(base_url, unescape(match.group("src")))


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


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", unescape(value))


def _clean(value: str) -> str | None:
    cleaned = _SPACE_RE.sub(" ", value).strip()
    return cleaned or None
