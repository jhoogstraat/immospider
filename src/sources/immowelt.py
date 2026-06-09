from __future__ import annotations

import re

from models import Listing, ListingSource

from .common import ExtractionConfig, extract_with_config

CONFIG = ExtractionConfig(
    source="Immowelt",
    source_color=0xF05A28,
    host="www.immowelt.de",
    inline_model_names=("classifieds", "classifiedSearch"),
    data_re=re.compile(r"(?:classifieds|classified|properties|items)", re.IGNORECASE),
    id_re=re.compile(r"/(?:expose|angebot)/(?P<id>[A-Za-z0-9_-]+)"),
    url_keys=("url", "href", "link", "detailUrl", "canonicalUrl", "seoUrl", "slug"),
    id_keys=("id", "@id", "listingId", "externalId", "classifiedId", "estateId"),
    title_keys=("title", "name", "headline", "shortDescription", "headlineText", "description"),
    price_keys=("price", "purchasePrice", "buyPrice", "priceValue"),
    area_keys=("livingSpace", "livingArea", "area", "size", "floorSpace"),
    rooms_keys=("numberOfRooms", "rooms", "roomCount", "numberOfRoomsValue"),
    provider_keys=("companyName", "provider", "contactName", "providerName", "seller", "brandName"),
    published_keys=("publishDate", "creationDate", "modifiedDate", "published", "datePublished"),
    image_keys=("image", "imageUrl", "picture", "pictureUrl", "thumbnailUrl", "coverImage"),
    utility_keys=("utilities", "serviceCharge", "additionalCosts", "operatingCosts", "ancillaryCosts", "heatingCosts"),
    listing_link_selectors=(
        '[data-test*="estate-card"] a[href*="/expose/"]',
        '[data-testid*="estate-card"] a[href*="/expose/"]',
        'article a[href*="/expose/"]',
        'a[href*="/expose/"]',
        'a[href*="/angebot/"]',
    ),
    card_container_keywords=("estate-card", "classified", "property", "teaser", "angebot", "expose"),
    address_selectors=('[data-test*="address"]', '[data-testid*="address"]', '[class*="address"]', '[class*="location"]'),
    provider_selectors=('[data-test*="provider"]', '[data-testid*="provider"]', '[class*="provider"]', '[class*="seller"]'),
    published_selectors=('[data-test*="date"]', '[data-testid*="date"]', '[class*="date"]'),
)
SOURCE = ListingSource(
    name=CONFIG.source,
    host=CONFIG.host,
    color=CONFIG.source_color,
    extract=lambda html, base_url: extract_listings(html, base_url),
)


def extract_listings(html: str, base_url: str = "https://www.immowelt.de") -> list[Listing]:
    return extract_with_config(html, base_url, CONFIG)
