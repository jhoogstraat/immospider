from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .cache import SeenListingCache
from .models import Listing
from .notifications import Notifier
from .pages import DEFAULT_URLS
from .scraper import DEFAULT_CONCURRENT_REQUESTS, DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN, scrape_listing_pages


@dataclass(frozen=True, slots=True)
class ScanResult:
    seen: int
    new: int
    notified: int


ScrapeListings = Callable[[Sequence[str], int, bool, bool, bool, int, int], list[Listing]]
ActivityLog = Callable[[str], None]




class ListingMonitor:
    def __init__(
        self,
        urls: Sequence[str] = DEFAULT_URLS,
        *,
        cache: SeenListingCache,
        notifier: Notifier,
        limit: int = 20,
        headless: bool = True,
        real_chrome: bool = False,
        solve_cloudflare: bool = False,
        concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
        concurrent_requests_per_domain: int = DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN,
        scraper: ScrapeListings | None = None,
        activity_log: ActivityLog | None = None,
    ) -> None:
        self.urls = tuple(urls)
        self.cache = cache
        self.notifier = notifier
        self.limit = limit
        self.headless = headless
        self.real_chrome = real_chrome
        self.solve_cloudflare = solve_cloudflare
        self.concurrent_requests = concurrent_requests
        self.concurrent_requests_per_domain = concurrent_requests_per_domain
        self.scraper = scraper or _scrape_listing_pages
        self.activity_log = activity_log

    def warm_cache(self) -> ScanResult:
        self._log(f"warming cache: fetching {len(self.urls)} page(s)")
        listings = self._fetch()
        result = ScanResult(seen=len(listings), new=self.cache.remember_many(listings), notified=0)
        self._log(f"cache warm: seen={result.seen} cached_new={result.new} notified=0")
        return result

    def scan_once(self) -> ScanResult:
        self._log(f"scan starting: fetching {len(self.urls)} page(s)")
        listings = self._fetch()
        new_count = 0
        notified = 0
        for listing in listings:
            if not self.cache.add_if_new(listing):
                continue
            new_count += 1
            if self.notifier.notify(listing):
                notified += 1
        result = ScanResult(seen=len(listings), new=new_count, notified=notified)
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

    def _fetch(self) -> list[Listing]:
        return self.scraper(
            self.urls,
            self.limit,
            self.headless,
            self.real_chrome,
            self.solve_cloudflare,
            self.concurrent_requests,
            self.concurrent_requests_per_domain,
        )

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
