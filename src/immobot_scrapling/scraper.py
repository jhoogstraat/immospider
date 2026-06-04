from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, AsyncGenerator

from scrapling.fetchers import AsyncStealthySession, StealthyFetcher
from scrapling.spiders import Request, Response, Spider

from .models import Listing, ListingSource
from .pages import DEFAULT_URL, DEFAULT_URLS, IMMOBILIENSCOUT24_URL, IMMOWELT_URL
from .sources import DEFAULT_SOURCES, source_for_url
from .sources.common import dedupe

DEFAULT_CONCURRENT_REQUESTS = 4
DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN = 1


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
    """Fetch listing search pages concurrently and return deduplicated, page-ordered listings."""
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
    """Fetch configured housing sources concurrently and return listings ready for notification."""
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
    if not urls:
        return []
    spider = _ListingPageSpider(
        urls,
        headless=headless,
        real_chrome=real_chrome,
        solve_cloudflare=solve_cloudflare,
        concurrent_requests=concurrent_requests,
        concurrent_requests_per_domain=concurrent_requests_per_domain,
    )
    result = spider.start()
    pages = [
        _FetchedPage(
            position=item["position"],
            requested_url=item["requested_url"],
            final_url=item["final_url"],
            html=item["html"],
        )
        for item in result.items
    ]
    pages.sort(key=lambda page: page.position)
    return pages


class _ListingPageSpider(Spider):
    name = "listing_pages"
    logging_level = logging.WARNING
    allowed_domains: set[str] = set()

    def __init__(
        self,
        urls: tuple[str, ...] | list[str],
        *,
        headless: bool,
        real_chrome: bool,
        solve_cloudflare: bool,
        concurrent_requests: int,
        concurrent_requests_per_domain: int,
    ) -> None:
        self._urls = tuple(urls)
        self._headless = headless
        self._real_chrome = real_chrome
        self._solve_cloudflare = solve_cloudflare
        self.concurrent_requests = concurrent_requests
        self.concurrent_requests_per_domain = concurrent_requests_per_domain
        super().__init__()

    def configure_sessions(self, manager: Any) -> None:
        manager.add(
            "stealth",
            AsyncStealthySession(
                headless=self._headless,
                real_chrome=self._real_chrome,
                block_webrtc=True,
                hide_canvas=True,
                locale="de-DE",
                timezone_id="Europe/Berlin",
                network_idle=True,
                wait=2000,
                timeout=90000,
                solve_cloudflare=self._solve_cloudflare,
                block_ads=True,
            ),
            default=True,
        )

    async def start_requests(self) -> AsyncGenerator[Request, None]:
        for position, url in enumerate(self._urls):
            yield Request(url, sid="stealth", callback=self.parse, dont_filter=True, meta={"position": position})

    async def parse(self, response: Response) -> AsyncGenerator[dict[str, Any], None]:
        yield {
            "position": response.meta["position"],
            "requested_url": response.request.url if response.request is not None else response.url,
            "final_url": response.url,
            "html": response.body.decode(response.encoding or "utf-8", errors="replace"),
        }


def _fetch_html(url: str, *, headless: bool, real_chrome: bool, solve_cloudflare: bool) -> str:
    response = StealthyFetcher.fetch(
        url,
        headless=headless,
        real_chrome=real_chrome,
        block_webrtc=True,
        hide_canvas=True,
        locale="de-DE",
        timezone_id="Europe/Berlin",
        network_idle=True,
        wait=2000,
        timeout=90000,
        solve_cloudflare=solve_cloudflare,
        block_ads=True,
    )
    return response.body.decode(response.encoding or "utf-8", errors="replace")


def listing_dicts(listings: list[Listing]) -> list[dict[str, Any]]:
    return [asdict(listing) for listing in listings]


def extract_listings(html: str, base_url: str = DEFAULT_URL) -> list[Listing]:
    """Extract listings with the extractor registered for ``base_url``."""
    return source_for_url(base_url).extract(html, base_url)
