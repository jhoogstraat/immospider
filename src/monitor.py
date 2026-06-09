from __future__ import annotations

import signal
from time import sleep
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
        self.activity_log: ActivityLog | None = activity_log

    def warm_cache(self) -> ScanResult:
        self._log(f"warming cache: fetching {len(self.urls)} page(s)")
        result = self._warm_with_listings(self._fetch_grouped_listings("cache warm"))
        return result

    def scan_once(self) -> ScanResult:
        self._log(f"scan starting: fetching {len(self.urls)} page(s)")
        result = self._scan_with_listings(self._fetch_grouped_listings("scan"))
        return result

    def run_forever(
        self,
        *,
        interval_seconds: float,
        max_scans: int | None = None,
    ) -> None:
        scans_completed = 0
        stop_requested = False
        original_sigterm = signal.getsignal(signal.SIGTERM)

        def request_stop(_signum: int, _frame: object) -> None:
            nonlocal stop_requested
            stop_requested = True
            self._log("stop requested; finishing current scan")

        _ = signal.signal(signal.SIGTERM, request_stop)
        try:
            self.warm_cache()
            while not stop_requested and (max_scans is None or scans_completed < max_scans):
                sleep(interval_seconds)
                if stop_requested:
                    break
                self.scan_once()
                scans_completed += 1
        finally:
            _ = signal.signal(signal.SIGTERM, original_sigterm)

    def _fetch_grouped_listings(self, operation: str) -> list[list[Listing]]:
        try:
            return scrape_listing_page_groups(
                [criterion.urls for criterion in self.criteria],
                self.limit,
                self.headless,
                self.real_chrome,
                self.concurrent_requests,
                self.concurrent_requests_per_domain,
            )
        except Exception as exc:
            self._log(f"{operation} failed: {exc}")
            return [[] for _ in self.criteria]



    def _warm_with_listings(self, grouped_listings: Sequence[Sequence[Listing]]) -> ScanResult:
        seen = 0
        new = 0
        for criterion, listings in zip(self.criteria, grouped_listings, strict=True):
            seen += len(listings)
            new += self.cache.remember_many(list(listings), self._cache_namespace(criterion))
        result = ScanResult(seen=seen, new=new, notified=0)
        self._log(f"cache warm: seen={result.seen} cached_new={result.new} notified=0")
        return result

    def _scan_with_listings(self, grouped_listings: Sequence[Sequence[Listing]]) -> ScanResult:
        seen = 0
        new_count = 0
        notified = 0
        for criterion, listings in zip(self.criteria, grouped_listings, strict=True):
            seen += len(listings)
            namespace = self._cache_namespace(criterion)
            for listing in listings:
                if not self.cache.add_if_new(listing, namespace):
                    continue
                new_count += 1
                try:
                    sent = criterion.notifier.notify(listing)
                except Exception as exc:
                    self._log(f"notification failed for {listing.url}: {exc}")
                    continue
                if sent:
                    notified += 1
        result = ScanResult(seen=seen, new=new_count, notified=notified)
        self._log(f"scan complete: seen={result.seen} new={result.new} notified={result.notified}")
        return result

    def _on_warm_listings(self, grouped_listings: list[list[Listing]]) -> None:
        _ = self._warm_with_listings(grouped_listings)

    def _on_scan_listings(self, grouped_listings: list[list[Listing]]) -> None:
        _ = self._scan_with_listings(grouped_listings)


    def _cache_namespace(self, criterion: SearchCriteria) -> str | None:
        if len(self.criteria) == 1 and criterion.name == "default":
            return None
        return criterion.name

    def _log(self, message: str) -> None:
        if self.activity_log is not None:
            self.activity_log(message)
