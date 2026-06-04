from __future__ import annotations

from pathlib import Path
import pytest

from immobot_scrapling.cache import SeenListingCache
from immobot_scrapling.models import Listing
from immobot_scrapling.monitor import ListingMonitor


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[Listing] = []

    def notify(self, listing: Listing) -> bool:
        self.sent.append(listing)
        return True


def test_first_monitor_fetch_warms_cache_without_notifications(tmp_path: Path) -> None:
    first = _listing("1", "Warm")
    second = _listing("2", "New")
    batches = [[first], [first, second]]
    notifier = RecordingNotifier()

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immobilienscout24.de/search"],
            cache=cache,
            notifier=notifier,
            scraper=lambda urls, limit, headless, real_chrome, solve_cloudflare, concurrent_requests, concurrent_requests_per_domain: batches.pop(0),
        )

        warm = monitor.warm_cache()
        scan = monitor.scan_once()

    assert warm.seen == 1
    assert warm.new == 1
    assert warm.notified == 0
    assert scan.seen == 2
    assert scan.new == 1
    assert scan.notified == 1
    assert notifier.sent == [second]


def test_monitor_run_forever_warms_before_first_scan(tmp_path: Path) -> None:
    warm_listing = _listing("1", "Warm")
    new_listing = _listing("2", "New")
    batches = [[warm_listing], [warm_listing, new_listing]]
    notifier = RecordingNotifier()

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immowelt.de/classified-search?order=DateDesc"],
            cache=cache,
            notifier=notifier,
            scraper=lambda urls, limit, headless, real_chrome, solve_cloudflare, concurrent_requests, concurrent_requests_per_domain: batches.pop(0),
        )

        monitor.run_forever(interval_seconds=1, max_scans=1, sleep=lambda seconds: None)

    assert notifier.sent == [new_listing]


def test_monitor_run_forever_propagates_keyboard_interrupt(tmp_path: Path) -> None:
    notifier = RecordingNotifier()

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immowelt.de/classified-search?order=DateDesc"],
            cache=cache,
            notifier=notifier,
            scraper=lambda urls, limit, headless, real_chrome, solve_cloudflare, concurrent_requests, concurrent_requests_per_domain: [_listing("1", "Warm")],
        )

        with pytest.raises(KeyboardInterrupt):
            monitor.run_forever(
                interval_seconds=1,
                sleep=lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt),
            )

def test_monitor_activity_log_reports_warm_and_scan(tmp_path: Path) -> None:
    first = _listing("1", "Warm")
    second = _listing("2", "New")
    batches = [[first], [first, second]]
    messages: list[str] = []

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immobilienscout24.de/search", "https://www.immowelt.de/classified-search?order=DateDesc"],
            cache=cache,
            notifier=RecordingNotifier(),
            scraper=lambda urls, limit, headless, real_chrome, solve_cloudflare, concurrent_requests, concurrent_requests_per_domain: batches.pop(0),
            activity_log=messages.append,
        )

        monitor.warm_cache()
        monitor.scan_once()

    assert messages == [
        "warming cache: fetching 2 page(s)",
        "cache warm: seen=1 cached_new=1 notified=0",
        "scan starting: fetching 2 page(s)",
        "scan complete: seen=2 new=1 notified=1",
    ]


def _listing(listing_id: str, title: str) -> Listing:
    return Listing(
        id=listing_id,
        title=title,
        url=f"https://www.example.test/expose/{listing_id}",
        address="Rheinallee 1, Düsseldorf",
        price_eur=1000.0,
        living_area_m2=70.0,
        rooms=2.0,
        provider=None,
        published=None,
        source="Example",
        source_color=0x123456,
        image_url=None,
        google_maps_url="https://www.google.com/maps/search/?api=1&query=Rheinallee+1%2C+D%C3%BCsseldorf",
    )
