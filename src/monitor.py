from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from cache import SeenListingCache
from models import Listing
from notifications import Notifier
from scraper import DEFAULT_CONCURRENT_REQUESTS, DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN, scrape_listing_page_groups


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

ScrapeListingGroups = Callable[[Sequence[tuple[str, ...]], int, bool, bool, int, int], list[list[Listing]]]
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
        concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
        concurrent_requests_per_domain: int = DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN,
        group_scraper: ScrapeListingGroups | None = None,
        activity_log: ActivityLog | None = None,
    ) -> None:
        self.criteria: tuple[SearchCriteria, ...] = (
            tuple(criteria) if criteria is not None else (SearchCriteria("default", tuple(urls or ()), notifier),)
        )
        if not self.criteria:
            raise ValueError("at least one search criteria is required")
        if any(not criterion.urls for criterion in self.criteria):
            raise ValueError("each search criteria requires at least one URL")
        self.urls: tuple[str, ...] = tuple(url for criterion in self.criteria for url in criterion.urls)
        self.cache: SeenListingCache = cache
        self.notifier: Notifier = notifier
        self.limit: int = limit
        self.headless: bool = headless
        self.real_chrome: bool = real_chrome
        self.concurrent_requests: int = concurrent_requests
        self.concurrent_requests_per_domain: int = concurrent_requests_per_domain
        self.group_scraper: ScrapeListingGroups = group_scraper or scrape_listing_page_groups
        self.activity_log: ActivityLog | None = activity_log

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
        _ = self.warm_cache()
        scans = 0
        while max_scans is None or scans < max_scans:
            if sleep(interval_seconds):
                break
            _ = self.scan_once()
            scans += 1

    def _fetch_by_criterion(self) -> list[list[Listing]]:
        return self.group_scraper(
            [criterion.urls for criterion in self.criteria],
            self.limit,
            self.headless,
            self.real_chrome,
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
