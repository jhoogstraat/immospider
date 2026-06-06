from __future__ import annotations
import logging
from dataclasses import dataclass
from collections.abc import AsyncGenerator
from typing import TypedDict, cast, override

from scrapling.fetchers import AsyncStealthySession
from models import Listing
from pages import fetch_options_for_url
from sources import source_for_url
from sources.common import dedupe
from scrapling.spiders import Request, Response, Spider
from scrapling.spiders.session import SessionManager

DEFAULT_CONCURRENT_REQUESTS = 4
DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN = 1
BROWSER_SETTLE_MS = 500
BROWSER_TIMEOUT_MS = 45000



@dataclass(frozen=True, slots=True)
class _FetchedListings:
    position: int
    listings: list[Listing]

class _SpiderItem(TypedDict):
    position: int
    listings: list[Listing]



def scrape_listing_page_groups(
    url_groups: tuple[tuple[str, ...], ...] | list[tuple[str, ...]],
    limit: int = 20,
    headless: bool = True,
    real_chrome: bool = False,
    concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
    concurrent_requests_per_domain: int = DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN,
) -> list[list[Listing]]:
    """Fetch and extract all criteria URLs in one Scrapling spider crawl, then split listings by criteria."""
    flat_urls = [url for urls in url_groups for url in urls]
    fetched_pages = _fetch_listings_concurrently(
        flat_urls,
        limit=limit,
        headless=headless,
        real_chrome=real_chrome,
        concurrent_requests=concurrent_requests,
        concurrent_requests_per_domain=concurrent_requests_per_domain,
    )
    groups: list[list[Listing]] = []
    position = 0
    for urls in url_groups:
        listings: list[Listing] = []
        for _ in urls:
            listings.extend(fetched_pages[position].listings)
            position += 1
        groups.append(dedupe(listings)[:limit])
    return groups




def _fetch_listings_concurrently(
    urls: tuple[str, ...] | list[str],
    *,
    limit: int,
    headless: bool,
    real_chrome: bool,
    concurrent_requests: int,
    concurrent_requests_per_domain: int,
) -> list[_FetchedListings]:
    if not urls:
        return []
    spider = _ListingPagesSpider(
        tuple(urls),
        limit=limit,
        headless=headless,
        real_chrome=real_chrome,
        concurrent_requests=concurrent_requests,
        concurrent_requests_per_domain=concurrent_requests_per_domain,
    )
    result = spider.start()
    spider_items = cast(list[_SpiderItem], result.items)
    fetched_pages = [
        _FetchedListings(
            position=item["position"],
            listings=item["listings"],
        )
        for item in spider_items
    ]
    fetched_pages.sort(key=lambda page: page.position)
    return fetched_pages


class _ListingPagesSpider(Spider):
    name: str | None = "listing_pages"
    logging_level: int = logging.WARNING

    def __init__(
        self,
        urls: tuple[str, ...],
        limit: int,
        *,
        headless: bool,
        real_chrome: bool,
        concurrent_requests: int,
        concurrent_requests_per_domain: int,
    ) -> None:
        self.urls: tuple[str, ...] = urls
        self.limit: int = limit
        self.headless: bool = headless
        self.real_chrome: bool = real_chrome
        self.concurrent_requests: int = concurrent_requests
        self.concurrent_requests_per_domain: int = concurrent_requests_per_domain
        super().__init__()

    @override
    def configure_sessions(self, manager: SessionManager) -> None:
        _ = manager.add(
            "stealth",
            AsyncStealthySession(
                headless=self.headless,
                real_chrome=self.real_chrome,
                block_webrtc=True,
                hide_canvas=True,
                locale="de-DE",
                timezone_id="Europe/Berlin",
                network_idle=False,
                wait=BROWSER_SETTLE_MS,
                timeout=BROWSER_TIMEOUT_MS,
                disable_resources=True,
                solve_cloudflare=False,
                block_ads=True,
                max_pages=self.concurrent_requests,
            ),
            default=True,
        )

    @override
    async def start_requests(self) -> AsyncGenerator[Request, None]:
        for position, url in enumerate(self.urls):
            yield Request(
                url,
                sid="stealth",
                callback=self.parse,
                meta={"position": position, "requested_url": url},
                **fetch_options_for_url(url),
            )

    @override
    async def parse(self, response: Response) -> AsyncGenerator[dict[str, object] | Request | None, None]:
        requested_url = cast(str, response.meta["requested_url"])
        position = cast(int, response.meta["position"])
        html = response.body.decode(response.encoding or "utf-8", errors="replace")
        yield {
            "position": position,
            "listings": source_for_url(requested_url).extract(html, requested_url)[: self.limit],
        }







