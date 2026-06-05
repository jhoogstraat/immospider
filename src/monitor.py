from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from cache import SeenListingCache
from models import Listing
from notifications import Notifier
from scraper import (
    DEFAULT_CONCURRENT_REQUESTS,
    DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN,
    scrape_listing_page_groups,
    scrape_listing_pages,
)


@dataclass(frozen=True, slots=True)
class ScanResult:
    seen: int
    new: int
    notified: int


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    name: str
    urls: tuple[str, ...]
    notifier: Notifier

ScrapeListings = Callable[[Sequence[str], int, bool, bool, bool, int, int], list[Listing]]
ScrapeListingGroups = Callable[[Sequence[tuple[str, ...]], int, bool, bool, bool, int, int], list[list[Listing]]]
ActivityLog = Callable[[str], None]




class ListingMonitor:
    def __init__(
        self,
        urls: Sequence[str] | None = None,
        *,
        cache: SeenListingCache,
        notifier: Notifier,
        criteria: Sequence[SearchCriteria] | None = None,
        limit: int = 20,
        headless: bool = True,
        real_chrome: bool = False,
        solve_cloudflare: bool = False,
        concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
        concurrent_requests_per_domain: int = DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN,
        scraper: ScrapeListings | None = None,
        group_scraper: ScrapeListingGroups | None = None,
        activity_log: ActivityLog | None = None,
    ) -> None:
        self.criteria = tuple(criteria) if criteria is not None else (SearchCriteria("default", tuple(urls or ()), notifier),)
        if not self.criteria:
            raise ValueError("at least one search criteria is required")
        if any(not criterion.urls for criterion in self.criteria):
            raise ValueError("each search criteria requires at least one URL")
        self.urls = tuple(url for criterion in self.criteria for url in criterion.urls)
        self.cache = cache
        self.notifier = notifier
        self.limit = limit
        self.headless = headless
        self.real_chrome = real_chrome
        self.solve_cloudflare = solve_cloudflare
        self.concurrent_requests = concurrent_requests
        self.concurrent_requests_per_domain = concurrent_requests_per_domain
        self.scraper = scraper
        self.group_scraper = group_scraper or _scrape_listing_page_groups
        self.activity_log = activity_log

    def warm_cache(self) -> ScanResult:
        self._log(f"warming cache: fetching {len(self.urls)} page(s)")
        seen = 0
        new = 0
        for criterion, listings in zip(self.criteria, self._fetch_by_criterion(), strict=True):
            seen += len(listings)
            new += self.cache.remember_many(listings, self._cache_namespace(criterion))
        result = ScanResult(seen=seen, new=new, notified=0)
        self._log(f"cache warm: seen={result.seen} cached_new={result.new} notified=0")
        return result

    def scan_once(self) -> ScanResult:
        self._log(f"scan starting: fetching {len(self.urls)} page(s)")
        seen = 0
        new_count = 0
        notified = 0
        for criterion, listings in zip(self.criteria, self._fetch_by_criterion(), strict=True):
            seen += len(listings)
            namespace = self._cache_namespace(criterion)
            for listing in listings:
                if not self.cache.add_if_new(listing, namespace):
                    continue
                new_count += 1
                if criterion.notifier.notify(listing):
                    notified += 1
        result = ScanResult(seen=seen, new=new_count, notified=notified)
        self._log(f"scan complete: seen={result.seen} new={result.new} notified={result.notified}")
        return result

    def run_forever(
        self,
        *,
        interval_seconds: float,
        max_scans: int | None = None,
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        self.warm_cache()
        scans = 0
        while max_scans is None or scans < max_scans:
            if sleep(interval_seconds):
                break
            self.scan_once()
            scans += 1

    def _fetch_by_criterion(self) -> list[list[Listing]]:
        if self.scraper is not None:
            return [
                self.scraper(
                    criterion.urls,
                    self.limit,
                    self.headless,
                    self.real_chrome,
                    self.solve_cloudflare,
                    self.concurrent_requests,
                    self.concurrent_requests_per_domain,
                )
                for criterion in self.criteria
            ]
        return self.group_scraper(
            [criterion.urls for criterion in self.criteria],
            self.limit,
            self.headless,
            self.real_chrome,
            self.solve_cloudflare,
            self.concurrent_requests,
            self.concurrent_requests_per_domain,
        )

    def _cache_namespace(self, criterion: SearchCriteria) -> str | None:
        if len(self.criteria) == 1 and criterion.name == "default":
            return None
        return criterion.name

    def _log(self, message: str) -> None:
        if self.activity_log is not None:
            self.activity_log(message)


def _scrape_listing_pages(
    urls: Sequence[str],
    limit: int,
    headless: bool,
    real_chrome: bool,
    solve_cloudflare: bool,
    concurrent_requests: int,
    concurrent_requests_per_domain: int,
) -> list[Listing]:
    return scrape_listing_pages(
        list(urls),
        limit=limit,
        headless=headless,
        real_chrome=real_chrome,
        solve_cloudflare=solve_cloudflare,
        concurrent_requests=concurrent_requests,
        concurrent_requests_per_domain=concurrent_requests_per_domain,
    )


def _scrape_listing_page_groups(
    url_groups: Sequence[tuple[str, ...]],
    limit: int,
    headless: bool,
    real_chrome: bool,
    solve_cloudflare: bool,
    concurrent_requests: int,
    concurrent_requests_per_domain: int,
) -> list[list[Listing]]:
    return scrape_listing_page_groups(
        list(url_groups),
        limit=limit,
        headless=headless,
        real_chrome=real_chrome,
        solve_cloudflare=solve_cloudflare,
        concurrent_requests=concurrent_requests,
        concurrent_requests_per_domain=concurrent_requests_per_domain,
    )
