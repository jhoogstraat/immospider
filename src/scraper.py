from __future__ import annotations
import logging
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass
from typing import TypedDict, cast, override

import anyio

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
    url_groups: Sequence[tuple[str, ...]],
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
    fetched_by_position = {
        item["position"]: _FetchedListings(
            position=item["position"],
            listings=item["listings"],
        )
        for item in spider_items
    }
    return [
        fetched_by_position.get(position, _FetchedListings(position=position, listings=[]))
        for position in range(len(urls))
    ]


class MonitoringSpider(Spider):
    name: str | None = "listing_monitor"
    logging_level: int = logging.WARNING

    def __init__(
        self,
        url_groups: Sequence[tuple[str, ...]],
        *,
        limit: int,
        interval_seconds: float,
        headless: bool,
        real_chrome: bool,
        concurrent_requests: int,
        concurrent_requests_per_domain: int,
        on_warm: Callable[[list[list[Listing]]], None],
        on_scan: Callable[[list[list[Listing]]], None],
        max_cycles: int | None = None,
        activity_log: Callable[[str], None] | None = None,
    ) -> None:
        self.url_groups: tuple[tuple[str, ...], ...] = tuple(tuple(group) for group in url_groups)
        if not self.url_groups:
            raise ValueError("at least one search criteria is required")
        if any(not group for group in self.url_groups):
            raise ValueError("each search criteria requires at least one URL")
        self._flat_urls: tuple[tuple[int, int, str], ...] = tuple(
            (group_index, url_index, url)
            for group_index, urls in enumerate(self.url_groups)
            for url_index, url in enumerate(urls)
        )
        self.limit: int = limit
        self.interval_seconds: float = interval_seconds
        self.headless: bool = headless
        self.real_chrome: bool = real_chrome
        self.concurrent_requests: int = concurrent_requests
        self.concurrent_requests_per_domain: int = concurrent_requests_per_domain
        self.on_warm: Callable[[list[list[Listing]]], None] = on_warm
        self.on_scan: Callable[[list[list[Listing]]], None] = on_scan
        self.max_cycles: int | None = max_cycles
        self.activity_log: Callable[[str], None] | None = activity_log
        self._cycle_results: dict[int, dict[tuple[int, int], list[Listing]]] = {}
        self._cycle_completed: dict[int, int] = {}
        self._lock: anyio.Lock = anyio.Lock()
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
        for group_index, url_index, url in self._flat_urls:
            yield self._request_for(cycle=0, group_index=group_index, url_index=url_index, url=url)

    def _request_for(self, *, cycle: int, group_index: int, url_index: int, url: str) -> Request:
        return Request(
            url,
            sid="stealth",
            callback=self.parse,
            meta={
                "cycle": cycle,
                "group_index": group_index,
                "url_index": url_index,
                "requested_url": url,
            },
            **fetch_options_for_url(url),
        )

    @override
    async def parse(self, response: Response) -> AsyncGenerator[dict[str, object] | Request | None, None]:
        requested_url = cast(str, response.meta["requested_url"])
        cycle = cast(int, response.meta["cycle"])
        group_index = cast(int, response.meta["group_index"])
        url_index = cast(int, response.meta["url_index"])
        html = response.body.decode(response.encoding or "utf-8", errors="replace")
        listings = source_for_url(requested_url).extract(html, requested_url)[: self.limit]
        for request in await self._record_url_result(
            cycle=cycle,
            group_index=group_index,
            url_index=url_index,
            listings=listings,
        ):
            yield request

    async def _record_url_result(
        self,
        *,
        cycle: int,
        group_index: int,
        url_index: int,
        listings: list[Listing],
    ) -> list[Request]:
        async with self._lock:
            results = self._cycle_results.setdefault(cycle, {})
            key = (group_index, url_index)
            if key in results:
                return []
            results[key] = listings
            completed = self._cycle_completed.get(cycle, 0) + 1
            self._cycle_completed[cycle] = completed
            if completed < len(self._flat_urls):
                return []

            grouped_listings: list[list[Listing]] = []
            for current_group_index, urls in enumerate(self.url_groups):
                group_listings: list[Listing] = []
                for current_url_index, _ in enumerate(urls):
                    group_listings.extend(results[(current_group_index, current_url_index)])
                grouped_listings.append(dedupe(group_listings)[: self.limit])
            del self._cycle_results[cycle]
            del self._cycle_completed[cycle]

        if cycle == 0:
            self.on_warm(grouped_listings)
        else:
            self.on_scan(grouped_listings)

        if self.max_cycles is not None and cycle + 1 >= self.max_cycles:
            return []

        await anyio.sleep(self.interval_seconds)
        return [
            self._request_for(cycle=cycle + 1, group_index=group_index, url_index=url_index, url=url)
            for group_index, url_index, url in self._flat_urls
        ]

    @override
    async def on_error(self, request: Request, error: Exception) -> None:
        cycle = cast(int, request.meta["cycle"])
        group_index = cast(int, request.meta["group_index"])
        url_index = cast(int, request.meta["url_index"])
        if self.activity_log is not None:
            self.activity_log(f"scan request failed: {request.url}: {error}")
        next_requests = await self._record_url_result(
            cycle=cycle,
            group_index=group_index,
            url_index=url_index,
            listings=[],
        )
        if self._engine is not None:
            for next_request in next_requests:
                self._engine._normalize_request(next_request)  # pyright: ignore[reportPrivateUsage]
                _ = await self._engine.scheduler.enqueue(next_request)


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







