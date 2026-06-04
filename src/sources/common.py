from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

from models import Listing

_JSON_SCRIPT_RE = re.compile(
    r'<script[^>]+(?:type=["\']application/(?:ld\+)?json["\']|id=["\']__NEXT_DATA__["\'])[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_SPACE_RE = re.compile(r"\s+")
_PRICE_RE = re.compile(r"(?P<value>[\d.]+(?:,\d+)?)\s*€")
_SIZE_RE = re.compile(r"(?P<value>[\d.]+(?:,\d+)?)\s*m²")
_ROOMS_RE = re.compile(r"(?P<value>\d+(?:,\d+)?)\s*(?:Zi|Zimmer)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ExtractionConfig:
    source: str
    source_color: int
    host: str
    inline_model_names: tuple[str, ...]
    data_re: re.Pattern[str]
    id_re: re.Pattern[str]
    url_keys: tuple[str, ...]
    id_keys: tuple[str, ...]
    title_keys: tuple[str, ...]
    price_keys: tuple[str, ...]
    area_keys: tuple[str, ...]
    rooms_keys: tuple[str, ...]
    provider_keys: tuple[str, ...]
    published_keys: tuple[str, ...]
    image_keys: tuple[str, ...]
    nested_listing_key: str | None = None


def extract_with_config(html: str, base_url: str, config: ExtractionConfig) -> list[Listing]:
    listings = _extract_from_json_scripts(html, base_url, config)
    listings.extend(_extract_from_inline_models(html, base_url, config))
    if not listings:
        listings = _extract_from_cards(html, base_url, config)
    return dedupe(listings)


def dedupe(listings: list[Listing]) -> list[Listing]:
    positions: dict[str, int] = {}
    deduped: list[Listing] = []
    for listing in listings:
        key = listing_key(listing)
        position = positions.get(key)
        if position is None:
            positions[key] = len(deduped)
            deduped.append(listing)
            continue
        if _listing_score(listing) > _listing_score(deduped[position]):
            deduped[position] = listing
    return deduped


def listing_key(listing: Listing) -> str:
    return f"{listing.source}:{listing.id}" if listing.id is not None else listing.url


def _extract_from_json_scripts(html: str, base_url: str, config: ExtractionConfig) -> list[Listing]:
    found: list[Listing] = []
    for match in _JSON_SCRIPT_RE.finditer(html):
        raw = unescape(match.group(1)).strip()
        if not raw or not config.data_re.search(raw):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        _walk_json(payload, found, base_url, config)
    return found


def _extract_from_inline_models(html: str, base_url: str, config: ExtractionConfig) -> list[Listing]:
    found: list[Listing] = []
    decoder = json.JSONDecoder()
    for name in config.inline_model_names:
        start = 0
        marker = f"{name}:"
        while True:
            marker_index = html.find(marker, start)
            if marker_index == -1:
                break
            json_start = marker_index + len(marker)
            while json_start < len(html) and html[json_start].isspace():
                json_start += 1
            try:
                payload, end = decoder.raw_decode(html[json_start:])
            except json.JSONDecodeError:
                start = json_start + 1
                continue
            _walk_json(payload, found, base_url, config)
            start = json_start + end
    return found


def _walk_json(value: Any, out: list[Listing], base_url: str, config: ExtractionConfig) -> None:
    if isinstance(value, dict):
        listing = _listing_from_mapping(value, base_url, config)
        if listing is not None:
            out.append(listing)
        for child in value.values():
            _walk_json(child, out, base_url, config)
    elif isinstance(value, list):
        for child in value:
            _walk_json(child, out, base_url, config)


def _listing_from_mapping(data: dict[str, Any], base_url: str, config: ExtractionConfig) -> Listing | None:
    source = data.get(config.nested_listing_key) if config.nested_listing_key is not None else None
    if not isinstance(source, dict):
        source = data

    url = _first_str(source, *config.url_keys)
    listing_id = _first_str(source, *config.id_keys)
    if listing_id is None:
        listing_id = _first_str(data, *config.id_keys)
    if url is None and listing_id is not None:
        url = f"/expose/{listing_id}"
    if url is None:
        return None
    absolute_url = urljoin(base_url, url)
    if not _is_listing_url(absolute_url, base_url, config):
        return None

    address = _address_from_mapping(source)
    image_url = _image_from_mapping(source, base_url, config)
    return Listing(
        id=listing_id or _id_from_url(absolute_url, config),
        title=_clean(_first_str(source, *config.title_keys)),
        url=absolute_url,
        address=_clean(address),
        price_eur=_first_number(source, *config.price_keys),
        living_area_m2=_first_number(source, *config.area_keys),
        rooms=_first_number(source, *config.rooms_keys),
        provider=_provider_from_mapping(source, config),
        published=_clean(_first_str(source, *config.published_keys) or _first_str(data, "@publishDate", "@modification", "@creation")),
        source=config.source,
        source_color=config.source_color,
        image_url=image_url,
        google_maps_url=_google_maps_url(address),
    )


def _extract_from_cards(html: str, base_url: str, config: ExtractionConfig) -> list[Listing]:
    out: list[Listing] = []
    pattern = r'href=["\'](?P<href>[^"\']*(?:/expose/|/angebot/)[A-Za-z0-9_-]+[^"\']*)["\']'
    for href_match in re.finditer(pattern, html):
        start = max(0, href_match.start() - 2500)
        end = min(len(html), href_match.end() + 2500)
        chunk = html[start:end]
        text = _strip_tags(chunk)
        url = urljoin(base_url, unescape(href_match.group("href")))
        if not _is_listing_url(url, base_url, config):
            continue
        title = _guess_title(chunk)
        out.append(
            Listing(
                id=_id_from_url(url, config),
                title=title,
                url=url,
                address=None,
                price_eur=_number_from_regex(_PRICE_RE, text),
                living_area_m2=_number_from_regex(_SIZE_RE, text),
                rooms=_number_from_regex(_ROOMS_RE, text),
                provider=None,
                published=None,
                source=config.source,
                source_color=config.source_color,
                image_url=_image_from_html(chunk, base_url),
                google_maps_url=None,
            )
        )
    return out


def _provider_from_mapping(data: dict[str, Any], config: ExtractionConfig) -> str | None:
    provider = _first_str(data, *config.provider_keys)
    if provider is None and isinstance(data.get("contactDetails"), dict):
        provider = _first_str(data["contactDetails"], "company", "firstname", "lastname", "name")
    return _clean(provider)


def _image_from_mapping(data: dict[str, Any], base_url: str, config: ExtractionConfig) -> str | None:
    value = _first_str(data, *config.image_keys)
    if value is not None:
        return urljoin(base_url, value)
    images = data.get("images") or data.get("pictures") or data.get("attachments")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, str) and image.strip():
                return urljoin(base_url, image)
            if isinstance(image, dict):
                value = _first_str(image, "url", "href", "src", "source", "large", "medium")
                if value is not None:
                    return urljoin(base_url, value)
    return None


def _image_from_html(html: str, base_url: str) -> str | None:
    match = re.search(r'<img[^>]+(?:src|data-src)=["\'](?P<src>[^"\']+)["\']', html, re.IGNORECASE)
    return urljoin(base_url, unescape(match.group("src"))) if match is not None else None


def _address_from_mapping(data: dict[str, Any]) -> str | None:
    address = data.get("address") or data.get("location")
    if isinstance(address, str):
        return address
    if not isinstance(address, dict):
        return _first_str(data, "addressDescription", "street", "postcode")
    description = _first_str(address, "description")
    if description:
        return description
    parts = [
        _first_str(address, "street", "streetAddress"),
        _first_str(address, "postcode", "postalCode"),
        _first_str(address, "city", "addressLocality"),
        _first_str(address, "quarter", "district"),
    ]
    return ", ".join(part for part in parts if part) or None


def _google_maps_url(address: str | None) -> str | None:
    cleaned = _clean(address)
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(cleaned)}" if cleaned is not None else None


def _listing_score(listing: Listing) -> int:
    return sum(
        value is not None
        for value in (
            listing.title,
            listing.address,
            listing.price_eur,
            listing.living_area_m2,
            listing.rooms,
            listing.provider,
            listing.published,
            listing.image_url,
            listing.google_maps_url,
        )
    )


def _first_str(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict):
            nested = _first_str(value, "value", "label", "text", "name", "url", "href", "path", "src")
            if nested:
                return nested
    return None


def _first_number(data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        number = _to_float(value)
        if number is not None:
            return number
        if isinstance(value, dict):
            number = _first_number(value, "value", "amount")
            if number is not None:
                return number
    return None


def _guess_title(chunk: str) -> str | None:
    match = re.search(r'<h[1-3][^>]*>(.*?)</h[1-3]>', chunk, re.IGNORECASE | re.DOTALL)
    if match is None:
        return None
    return _strip_tags(match.group(1))


def _strip_tags(value: str) -> str:
    return _clean(re.sub(r"<[^>]+>", " ", unescape(value))) or ""


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _SPACE_RE.sub(" ", unescape(value)).strip()
    return cleaned or None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().replace(".", "").replace(",", ".")
        normalized = re.sub(r"[^0-9.-]", "", normalized)
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _number_from_regex(pattern: re.Pattern[str], text: str) -> float | None:
    match = pattern.search(text)
    if match is None:
        return None
    return _to_float(match.group("value"))


def _is_listing_url(url: str, base_url: str, config: ExtractionConfig) -> bool:
    parsed = urlparse(url)
    base_host = urlparse(base_url).netloc
    if parsed.netloc and base_host and parsed.netloc != base_host:
        return False
    return config.id_re.search(parsed.path) is not None


def _id_from_url(url: str, config: ExtractionConfig) -> str | None:
    match = config.id_re.search(urlparse(url).path)
    return match.group("id") if match else None
