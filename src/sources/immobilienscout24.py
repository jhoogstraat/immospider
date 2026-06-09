from __future__ import annotations

import re

from models import Listing, ListingSource

from .common import ExtractionConfig, extract_with_config

CONFIG = ExtractionConfig(
    source="ImmobilienScout24",
    source_color=0x00AEEF,
    host="www.immobilienscout24.de",
    inline_model_names=("resultListModel", "searchResponseModel"),
    data_re=re.compile(r"(?:resultListModel|searchResponseModel|listings|realEstates)", re.IGNORECASE),
    id_re=re.compile(r"/(?:expose|angebot)/(?P<id>[A-Za-z0-9_-]+)"),
    url_keys=("url", "href", "link", "detailUrl", "exposeUrl", "canonicalUrl"),
    id_keys=("id", "@id", "realEstateId", "exposeId", "listingId", "externalId"),
    title_keys=("title", "name", "headline", "shortDescription"),
    price_keys=("price", "rent", "coldRent", "baseRent", "totalRent", "calculatedTotalRent"),
    area_keys=("livingSpace", "livingArea", "area", "size"),
    rooms_keys=("numberOfRooms", "rooms", "roomCount"),
    provider_keys=("companyName", "realtorCompanyName", "provider", "contactName"),
    published_keys=("publishDate", "creationDate", "modifiedDate", "published", "datePublished"),
    image_keys=("image", "imageUrl", "picture", "pictureUrl", "titlePicture"),
    utility_keys=("utilities", "serviceCharge", "additionalCosts", "operatingCosts", "heatingCosts"),
    nested_listing_key="resultlist.realEstate",
    listing_link_selectors=(
        '[data-testid*="result-list-entry"] a[href*="/expose/"]',
        'article a[href*="/expose/"]',
        'a[href*="/expose/"]',
    ),
    card_container_keywords=("result-list-entry", "result-list", "expose", "is24"),
    address_selectors=('[data-testid*="address"]', '[class*="address"]', '[class*="location"]'),
    provider_selectors=('[data-testid*="provider"]', '[class*="provider"]', '[class*="realtor"]'),
    published_selectors=('[data-testid*="date"]', '[class*="date"]'),
)
SOURCE = ListingSource(
    name=CONFIG.source,
    host=CONFIG.host,
    color=CONFIG.source_color,
    extract=lambda html, base_url: extract_listings(html, base_url),
)


def extract_listings(html: str, base_url: str = "https://www.immobilienscout24.de") -> list[Listing]:
    return extract_with_config(html, base_url, CONFIG)
