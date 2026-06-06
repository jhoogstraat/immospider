from __future__ import annotations
import logging
from dataclasses import asdict, dataclass
from typing import Any
from scrapling.fetchers import AsyncStealthySession, StealthyFetcher
from models import Listing
from pages import fetch_options_for_url
from sources import source_for_url
from sources.common import dedupe
from scrapling.spiders import Request, Response, Spider

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
    url: str,
    limit: int = 20,
    headless: bool = True,
    real_chrome: bool = False,
) -> list[Listing]:
    """Fetch one listing search page and return listings in page order."""
    source = source_for_url(url)
    html = _fetch_html(url, headless=headless, real_chrome=real_chrome)
    listings = source.extract(html, url)
    return listings[:limit]


def scrape_listing_pages(
    urls: tuple[str, ...] | list[str],
    limit: int = 20,
    headless: bool = True,
    real_chrome: bool = False,
    concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
    concurrent_requests_per_domain: int = DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN,
) -> list[Listing]:
    """Fetch listing search pages and return deduplicated, page-ordered listings."""
    pages = _fetch_pages_concurrently(
        urls,
        headless=headless,
        real_chrome=real_chrome,
        concurrent_requests=concurrent_requests,
        concurrent_requests_per_domain=concurrent_requests_per_domain,
    )
    listings: list[Listing] = []
    for page in pages:
        source = source_for_url(page.requested_url)
        listings.extend(source.extract(page.html, page.requested_url)[:limit])
    return dedupe(listings)[:limit]

def scrape_listing_page_groups(
    url_groups: tuple[tuple[str, ...], ...] | list[tuple[str, ...]],
    limit: int = 20,
    headless: bool = True,
    real_chrome: bool = False,
    concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
    concurrent_requests_per_domain: int = DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN,
) -> list[list[Listing]]:
    """Fetch all criteria URLs in one Scrapling spider crawl, then split listings back by criteria."""
    flat_urls = [url for urls in url_groups for url in urls]
    pages = _fetch_pages_concurrently(
        flat_urls,
        headless=headless,
        real_chrome=real_chrome,
        concurrent_requests=concurrent_requests,
        concurrent_requests_per_domain=concurrent_requests_per_domain,
    )
    pages_by_position = {page.position: page for page in pages}
    groups: list[list[Listing]] = []
    position = 0
    for urls in url_groups:
        listings: list[Listing] = []
        for url in urls:
            page = pages_by_position[position]
            source = source_for_url(url)
            listings.extend(source.extract(page.html, url)[:limit])
            position += 1
        groups.append(dedupe(listings)[:limit])
    return groups




def _fetch_pages_concurrently(
    urls: tuple[str, ...] | list[str],
    *,
    headless: bool,
    real_chrome: bool,
    concurrent_requests: int,
    concurrent_requests_per_domain: int,
) -> list[_FetchedPage]:
    if not urls:
        return []
    spider = _ListingPagesSpider(
        tuple(urls),
        headless=headless,
        real_chrome=real_chrome,
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


class _ListingPagesSpider(Spider):
    name = "listing_pages"
    logging_level = logging.WARNING

    def __init__(
        self,
        urls: tuple[str, ...],
        *,
        headless: bool,
        real_chrome: bool,
        concurrent_requests: int,
        concurrent_requests_per_domain: int,
    ) -> None:
        self.urls = urls
        self.headless = headless
        self.real_chrome = real_chrome
        self.concurrent_requests = concurrent_requests
        self.concurrent_requests_per_domain = concurrent_requests_per_domain
        super().__init__()

    def configure_sessions(self, manager) -> None:
        manager.add(
            "stealth",
            AsyncStealthySession(
                **_browser_options(
                    page_options={},
                    headless=self.headless,
                    real_chrome=self.real_chrome,
                    max_pages=self.concurrent_requests,
                )
            ),
            default=True,
        )

    async def start_requests(self):
        for position, url in enumerate(self.urls):
            yield Request(
                url,
                sid="stealth",
                callback=self.parse,
                meta={"position": position, "requested_url": url},
                **_browser_options(
                    page_options=fetch_options_for_url(url),
                    headless=self.headless,
                    real_chrome=self.real_chrome,
                    max_pages=self.concurrent_requests,
                ),
            )

    async def parse(self, response: Response):
        yield {
            "position": response.meta["position"],
            "requested_url": response.meta["requested_url"],
            "final_url": response.url,
            "html": response.body.decode(response.encoding or "utf-8", errors="replace"),
        }




def _browser_options(
    *,
    page_options: dict[str, object],
    headless: bool,
    real_chrome: bool,
    max_pages: int = 1,
) -> dict[str, Any]:
    options: dict[str, Any] = {
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
        "solve_cloudflare": False,
        "block_ads": True,
        "max_pages": max_pages,
    }
    options.update(page_options)
    return options


def _fetch_response(url: str, *, headless: bool, real_chrome: bool) -> Any:
    return StealthyFetcher.fetch(
        url,
        **_browser_options(
            page_options=fetch_options_for_url(url),
            headless=headless,
            real_chrome=real_chrome,
        ),
    )


def _fetch_html(url: str, *, headless: bool, real_chrome: bool) -> str:
    response = _fetch_response(url, headless=headless, real_chrome=real_chrome)
    return response.body.decode(response.encoding or "utf-8", errors="replace")


def listing_dicts(listings: list[Listing]) -> list[dict[str, Any]]:
    return [asdict(listing) for listing in listings]


def extract_listings(html: str, base_url: str) -> list[Listing]:
    """Extract listings with the extractor registered for ``base_url``."""
    return source_for_url(base_url).extract(html, base_url)
