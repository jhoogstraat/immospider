from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

from scrapling.parser import Selector

from models import Listing

_SPACE_RE = re.compile(r"\s+")
_PRICE_RE = re.compile(r"(?P<value>[\d.]+(?:,\d+)?)\s*€")
_UTILITY_RE = re.compile(r"(?:Nebenkosten|Betriebskosten|Utilities)\D{0,40}(?P<value>[\d.]+(?:,\d+)?)\s*€", re.IGNORECASE)
_SIZE_RE = re.compile(r"(?P<value>[\d.]+(?:,\d+)?)\s*m²")
_ROOMS_RE = re.compile(r"(?P<value>\d+(?:,\d+)?)\s*(?:Zi|Zimmer)", re.IGNORECASE)
_JSON_SCRIPT_SELECTORS = ('script[type="application/json"]', 'script[type="application/ld+json"]', 'script#__NEXT_DATA__')
_LISTING_LINK_SELECTORS = ('a[href*="/expose/"]', 'a[href*="/angebot/"]')
_HEADING_SELECTORS = ("h1::text", "h2::text", "h3::text", '[data-testid*="title"]::text', '[data-test*="title"]::text')
_LISTING_CONTAINERS = ("article", "li", "section", "div")


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
    utility_keys: tuple[str, ...] = ()
    nested_listing_key: str | None = None
    listing_link_selectors: tuple[str, ...] = _LISTING_LINK_SELECTORS
    card_container_keywords: tuple[str, ...] = ()
    address_selectors: tuple[str, ...] = ()
    provider_selectors: tuple[str, ...] = ()
    published_selectors: tuple[str, ...] = ()


def extract_with_config(html: str, base_url: str, config: ExtractionConfig) -> list[Listing]:
    page = Selector(html)
    listings = _extract_from_json_scripts(page, base_url, config)
    listings.extend(_extract_from_inline_models(page, base_url, config))
    if not listings:
        listings = _extract_from_cards(page, base_url, config)
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


def _extract_from_json_scripts(page: Selector, base_url: str, config: ExtractionConfig) -> list[Listing]:
    found: list[Listing] = []
    for script in _json_script_elements(page):
        raw = str(script.text or "")
        if not config.data_re.search(raw):
            continue
        try:
            payload = script.json()
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
        _walk_json(payload, found, base_url, config)
    return found


def _json_script_elements(page: Selector) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for css_selector in _JSON_SCRIPT_SELECTORS:
        for script in page.css(css_selector):
            text = _clean(str(script.text or ""))
            if text is not None and text not in seen:
                seen.add(text)
                out.append(script)
    return out


def _extract_from_inline_models(page: Selector, base_url: str, config: ExtractionConfig) -> list[Listing]:
    found: list[Listing] = []
    decoder = json.JSONDecoder()
    for script in page.find_all("script", config.data_re):
        text = str(script.text or "")
        for name in config.inline_model_names:
            start = 0
            marker = f"{name}:"
            while True:
                marker_index = text.find(marker, start)
                if marker_index == -1:
                    break
                json_start = marker_index + len(marker)
                while json_start < len(text) and text[json_start].isspace():
                    json_start += 1
                try:
                    payload, end = decoder.raw_decode(text[json_start:])
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
    price_eur, price_label = _price_from_mapping(source, config.price_keys)
    return Listing(
        id=listing_id or _id_from_url(absolute_url, config),
        title=_clean(_first_str(source, *config.title_keys)),
        url=absolute_url,
        address=_clean(address),
        price_eur=price_eur,
        price_label=price_label,
        utilities_eur=_first_number(source, *config.utility_keys),
        living_area_m2=_first_number(source, *config.area_keys),
        rooms=_first_number(source, *config.rooms_keys),
        provider=_provider_from_mapping(source, config),
        published=_clean(_first_str(source, *config.published_keys) or _first_str(data, "@publishDate", "@modification", "@creation")),
        source=config.source,
        source_color=config.source_color,
        image_url=image_url,
        google_maps_url=_google_maps_url(address),
    )


def _extract_from_cards(page: Selector, base_url: str, config: ExtractionConfig) -> list[Listing]:
    out: list[Listing] = []
    for link in _listing_links(page, config):
        href = _attr(link, "href")
        if href is None:
            continue
        url = urljoin(base_url, href)
        if not _is_listing_url(url, base_url, config):
            continue
        card = _listing_container(link, config) or link
        text = _selector_text(card)
        address = _first_css_all_text(card, config.address_selectors)
        price_eur = _number_from_element(card, _PRICE_RE, text)
        out.append(
            Listing(
                id=_id_from_url(url, config),
                title=_heading_text(card) or _heading_text(link) or _selector_text(link),
                url=url,
                address=address,
                price_eur=price_eur,
                price_label=_price_label_from_text(text),
                utilities_eur=_number_from_regex(_UTILITY_RE, text),
                living_area_m2=_number_from_element(card, _SIZE_RE, text),
                rooms=_number_from_element(card, _ROOMS_RE, text),
                provider=_first_css_all_text(card, config.provider_selectors),
                published=_first_css_all_text(card, config.published_selectors),
                source=config.source,
                source_color=config.source_color,
                image_url=_image_from_element(card, base_url),
                google_maps_url=_google_maps_url(address),
            )
        )
    return out


def _listing_links(page: Selector, config: ExtractionConfig) -> list[Any]:
    seen: set[str] = set()
    links: list[Any] = []
    for css_selector in config.listing_link_selectors:
        for link in page.css(css_selector):
            href = _attr(link, "href")
            if href is not None and href not in seen:
                seen.add(href)
                links.append(link)
    for link in [*page.find_all("a", {"href*": "/expose/"}), *page.find_all("a", {"href*": "/angebot/"})]:
        href = _attr(link, "href")
        if href is not None and href not in seen:
            seen.add(href)
            links.append(link)
    return links


def _listing_container(element: Any, config: ExtractionConfig) -> Any | None:
    for ancestor in _ancestors(element):
        if any(keyword in _attributes_text(ancestor) for keyword in config.card_container_keywords):
            return ancestor
    return element.find_ancestor(lambda ancestor: ancestor.tag in _LISTING_CONTAINERS)


def _ancestors(element: Any) -> list[Any]:
    ancestors: list[Any] = []
    current = element.parent
    while current is not None:
        ancestors.append(current)
        current = current.parent
    return ancestors


def _attributes_text(element: Any) -> str:
    return " ".join(str(value) for value in element.attrib.values())


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


def _image_from_element(element: Any, base_url: str) -> str | None:
    src = _css_text(element, "img::attr(src)") or _css_text(element, "img::attr(data-src)")
    return urljoin(base_url, src) if src is not None else None


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
            listing.address,
            listing.price_eur,
            listing.price_label,
            listing.utilities_eur,
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

def _price_from_mapping(data: dict[str, Any], keys: tuple[str, ...]) -> tuple[float | None, str | None]:
    for key in keys:
        value = data.get(key)
        number = _to_float(value)
        if number is not None:
            return number, _price_label_from_key(key)
        if isinstance(value, dict):
            number = _first_number(value, "value", "amount")
            if number is not None:
                return number, _price_label_from_key(key)
    return None, None


def _price_label_from_key(key: str) -> str | None:
    normalized = key.lower()
    if any(part in normalized for part in ("warm", "total", "gross")):
        return "warm"
    if any(part in normalized for part in ("cold", "base", "net", "kalt")):
        return "cold"
    return None


def _price_label_from_text(text: str) -> str | None:
    normalized = text.casefold()
    if "warmmiete" in normalized or "warm rent" in normalized:
        return "warm"
    if "kaltmiete" in normalized or "cold rent" in normalized:
        return "cold"
    return None


def _heading_text(element: Any) -> str | None:
    for selector in _HEADING_SELECTORS:
        value = _css_text(element, selector)
        if value is not None:
            return value
    return _first_css_all_text(element, ("h1", "h2", "h3"))


def _selector_text(element: Any) -> str:
    return _clean(str(element.get_all_text(ignore_tags=("script", "style")) or "")) or ""


def _css_text(element: Any, selector: str) -> str | None:
    value = element.css(selector).get()
    return _clean(str(value)) if value is not None else None


def _attr(element: Any, name: str) -> str | None:
    value = element.attrib.get(name)
    return _clean(str(value)) if value is not None else None


def _first_css_all_text(element: Any, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        match = element.css(selector)
        if match:
            text = _clean(str(match[0].get_all_text(ignore_tags=("script", "style")) or ""))
            if text is not None:
                return text
    return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _SPACE_RE.sub(" ", value).strip()
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


def _number_from_element(element: Any, pattern: re.Pattern[str], fallback_text: str) -> float | None:
    match = element.find_by_regex(pattern)
    if match is not None:
        value = match.re_first(pattern)
        if value is not None:
            return _to_float(value)
    return _number_from_regex(pattern, fallback_text)


def _is_listing_url(url: str, base_url: str, config: ExtractionConfig) -> bool:
    parsed = urlparse(url)
    base_host = urlparse(base_url).netloc
    if parsed.netloc and base_host and parsed.netloc != base_host:
        return False
    return config.id_re.search(parsed.path) is not None


def _id_from_url(url: str, config: ExtractionConfig) -> str | None:
    match = config.id_re.search(urlparse(url).path)
    return match.group("id") if match else None
