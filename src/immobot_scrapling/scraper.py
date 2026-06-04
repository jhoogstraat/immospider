from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any
from scrapling.fetchers import StealthyFetcher
from .models import Listing, ListingSource
from .pages import DEFAULT_URL, DEFAULT_URLS, IMMOBILIENSCOUT24_URL, IMMOWELT_URL
from .sources import DEFAULT_SOURCES, source_for_url
from .sources.common import dedupe

DEFAULT_CONCURRENT_REQUESTS = 4
DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN = 1
BROWSER_SETTLE_MS = 500
BROWSER_TIMEOUT_MS = 45000



@dataclass(frozen=True, slots=True)
class _FetchedPage:
    position: int
    requested_url: str
    final_url: str
    html: str


def scrape_latest_listings(
    url: str = DEFAULT_URL,
    limit: int = 20,
    headless: bool = True,
    real_chrome: bool = False,
    solve_cloudflare: bool = False,
) -> list[Listing]:
    """Fetch one listing search page and return listings in page order."""
    source = source_for_url(url)
    html = _fetch_html(url, headless=headless, real_chrome=real_chrome, solve_cloudflare=solve_cloudflare)
    listings = source.extract(html, url)
    return listings[:limit]


def scrape_listing_pages(
    urls: tuple[str, ...] | list[str] = DEFAULT_URLS,
    limit: int = 20,
    headless: bool = True,
    real_chrome: bool = False,
    solve_cloudflare: bool = False,
    concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
    concurrent_requests_per_domain: int = DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN,
) -> list[Listing]:
    """Fetch listing search pages and return deduplicated, page-ordered listings."""
    pages = _fetch_pages_concurrently(
        urls,
        headless=headless,
        real_chrome=real_chrome,
        solve_cloudflare=solve_cloudflare,
        concurrent_requests=concurrent_requests,
        concurrent_requests_per_domain=concurrent_requests_per_domain,
    )
    listings: list[Listing] = []
    for page in pages:
        source = source_for_url(page.requested_url)
        listings.extend(source.extract(page.html, page.requested_url)[:limit])
    return dedupe(listings)[:limit]


def scrape_sources(
    sources: tuple[ListingSource, ...] | list[ListingSource] = DEFAULT_SOURCES,
    limit: int = 20,
    headless: bool = True,
    real_chrome: bool = False,
    solve_cloudflare: bool = False,
    concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
    concurrent_requests_per_domain: int = DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN,
) -> list[Listing]:
    """Fetch configured housing sources and return listings ready for notification."""
    pages = _fetch_pages_concurrently(
        [source.url for source in sources],
        headless=headless,
        real_chrome=real_chrome,
        solve_cloudflare=solve_cloudflare,
        concurrent_requests=concurrent_requests,
        concurrent_requests_per_domain=concurrent_requests_per_domain,
    )
    sources_by_url = {source.url: source for source in sources}
    listings: list[Listing] = []
    for page in pages:
        source = sources_by_url[page.requested_url]
        listings.extend(source.extract(page.html, page.requested_url)[:limit])
    return dedupe(listings)[:limit]


def _fetch_pages_concurrently(
    urls: tuple[str, ...] | list[str],
    *,
    headless: bool,
    real_chrome: bool,
    solve_cloudflare: bool,
    concurrent_requests: int,
    concurrent_requests_per_domain: int,
) -> list[_FetchedPage]:
    _ = concurrent_requests, concurrent_requests_per_domain
    pages = [
        _fetch_page(position, url, headless=headless, real_chrome=real_chrome, solve_cloudflare=solve_cloudflare)
        for position, url in enumerate(urls)
    ]
    pages.sort(key=lambda page: page.position)
    return pages


def _fetch_page(
    position: int,
    url: str,
    *,
    headless: bool,
    real_chrome: bool,
    solve_cloudflare: bool,
) -> _FetchedPage:
    response = _fetch_response(url, headless=headless, real_chrome=real_chrome, solve_cloudflare=solve_cloudflare)
    return _FetchedPage(
        position=position,
        requested_url=url,
        final_url=response.url,
        html=response.body.decode(response.encoding or "utf-8", errors="replace"),
    )


def _browser_options(*, headless: bool, real_chrome: bool, solve_cloudflare: bool, max_pages: int = 1) -> dict[str, Any]:
    return {
        "headless": headless,
        "real_chrome": real_chrome,
        "block_webrtc": True,
        "hide_canvas": True,
        "locale": "de-DE",
        "timezone_id": "Europe/Berlin",
        "network_idle": False,
        "wait": BROWSER_SETTLE_MS,
        "timeout": BROWSER_TIMEOUT_MS,
        "disable_resources": True,
        "solve_cloudflare": solve_cloudflare,
        "block_ads": True,
        "max_pages": max_pages,
    }


def _fetch_response(url: str, *, headless: bool, real_chrome: bool, solve_cloudflare: bool) -> Any:
    return StealthyFetcher.fetch(
        url,
        **_browser_options(headless=headless, real_chrome=real_chrome, solve_cloudflare=solve_cloudflare),
    )


def _fetch_html(url: str, *, headless: bool, real_chrome: bool, solve_cloudflare: bool) -> str:
    response = _fetch_response(url, headless=headless, real_chrome=real_chrome, solve_cloudflare=solve_cloudflare)
    return response.body.decode(response.encoding or "utf-8", errors="replace")


def listing_dicts(listings: list[Listing]) -> list[dict[str, Any]]:
    return [asdict(listing) for listing in listings]


def extract_listings(html: str, base_url: str = DEFAULT_URL) -> list[Listing]:
    """Extract listings with the extractor registered for ``base_url``."""
    return source_for_url(base_url).extract(html, base_url)
