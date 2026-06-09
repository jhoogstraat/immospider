from __future__ import annotations

from pathlib import Path


from cache import SeenListingCache
from models import Listing
from monitor import ListingMonitor, SearchCriteria


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[Listing] = []

    def notify(self, listing: Listing) -> bool:
        self.sent.append(listing)
        return True


class CriteriaRecordingNotifier:
    def __init__(self, name: str) -> None:
        self.name = name
        self.sent: list[tuple[str, Listing]] = []

    def notify(self, listing: Listing) -> bool:
        self.sent.append((self.name, listing))
        return True


def test_first_monitor_fetch_warms_cache_without_notifications(tmp_path: Path, monkeypatch) -> None:
    first = _listing("1", "Warm")
    second = _listing("2", "New")
    batches = [[first], [first, second]]
    notifier = RecordingNotifier()

    def fake_scrape(url_groups, limit, headless, real_chrome, concurrent_requests, concurrent_requests_per_domain):
        return [batches.pop(0)]

    monkeypatch.setattr("monitor.scrape_listing_page_groups", fake_scrape)

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immobilienscout24.de/search"],
            cache=cache,
            notifier=notifier,
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


def test_monitor_run_forever_warms_before_first_scan(tmp_path: Path, monkeypatch) -> None:
    warm_listing = _listing("1", "Warm")
    new_listing = _listing("2", "New")
    notifier = RecordingNotifier()

    class FakeMonitoringSpider:
        def __init__(self, url_groups, **kwargs) -> None:
            assert tuple(url_groups) == (("https://www.immowelt.de/classified-search?order=DateDesc",),)
            assert kwargs["interval_seconds"] == 1
            assert kwargs["max_cycles"] == 2
            self.on_warm = kwargs["on_warm"]
            self.on_scan = kwargs["on_scan"]

        def pause(self) -> None:
            return None

        def start(self):
            self.on_warm([[warm_listing]])
            self.on_scan([[warm_listing, new_listing]])
            return None

    monkeypatch.setattr("monitor.MonitoringSpider", FakeMonitoringSpider)

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immowelt.de/classified-search?order=DateDesc"],
            cache=cache,
            notifier=notifier,
        )

        monitor.run_forever(interval_seconds=1, max_scans=1)

    assert notifier.sent == [new_listing]


def test_monitor_run_forever_uses_one_spider_for_multiple_scans(tmp_path: Path, monkeypatch) -> None:
    listings = [_listing("1", "Warm"), _listing("2", "First"), _listing("3", "Second")]
    notifier = RecordingNotifier()
    constructed = 0

    class FakeMonitoringSpider:
        def __init__(self, url_groups, **kwargs) -> None:
            nonlocal constructed
            constructed += 1
            assert kwargs["max_cycles"] == 3
            self.on_warm = kwargs["on_warm"]
            self.on_scan = kwargs["on_scan"]

        def pause(self) -> None:
            return None

        def start(self):
            self.on_warm([[listings[0]]])
            self.on_scan([[listings[0], listings[1]]])
            self.on_scan([[listings[0], listings[2]]])
            return None

    monkeypatch.setattr("monitor.MonitoringSpider", FakeMonitoringSpider)

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immowelt.de/classified-search?order=DateDesc"],
            cache=cache,
            notifier=notifier,
        )

        monitor.run_forever(interval_seconds=1, max_scans=2)

    assert constructed == 1
    assert notifier.sent == listings[1:]

def test_named_criteria_notify_separate_channels_and_cache_namespaces(tmp_path: Path) -> None:
    warm_listing = _listing("0", "Warm")
    shared = _listing("1", "Shared")
    duesseldorf = CriteriaRecordingNotifier("duesseldorf")
    cologne = CriteriaRecordingNotifier("cologne")
    grouped_inputs = [
        [[warm_listing], [warm_listing]],
        [[shared], [shared]],
    ]

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            cache=cache,
            notifier=duesseldorf,
            criteria=(
                SearchCriteria(
                    "duesseldorf",
                    ("https://www.immobilienscout24.de/duesseldorf", "https://www.immowelt.de/duesseldorf"),
                    duesseldorf,
                ),
                SearchCriteria("cologne", ("https://www.immobilienscout24.de/cologne",), cologne),
            ),
        )

        warm = monitor._warm_with_listings(grouped_inputs[0])
        scan = monitor._scan_with_listings(grouped_inputs[1])

    assert tuple(criterion.urls for criterion in monitor.criteria) == (
        ("https://www.immobilienscout24.de/duesseldorf", "https://www.immowelt.de/duesseldorf"),
        ("https://www.immobilienscout24.de/cologne",),
    )
    assert warm == type(warm)(seen=2, new=2, notified=0)
    assert scan == type(scan)(seen=2, new=2, notified=2)
    assert duesseldorf.sent == [("duesseldorf", shared)]
    assert cologne.sent == [("cologne", shared)]

def test_default_monitor_fetches_all_criteria_in_one_group_scrape(tmp_path: Path, monkeypatch) -> None:
    duesseldorf_listing = _listing("1", "Düsseldorf")
    cologne_listing = _listing("2", "Cologne")
    grouped_calls = []

    def fake_scrape(url_groups, limit, headless, real_chrome, concurrent_requests, concurrent_requests_per_domain):
        grouped_calls.append(tuple(url_groups))
        return [[duesseldorf_listing], [cologne_listing]]

    monkeypatch.setattr("monitor.scrape_listing_page_groups", fake_scrape)

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            cache=cache,
            notifier=RecordingNotifier(),
            criteria=(
                SearchCriteria("duesseldorf", ("https://www.immobilienscout24.de/duesseldorf",), RecordingNotifier()),
                SearchCriteria("cologne", ("https://www.immowelt.de/cologne",), RecordingNotifier()),
            ),
        )

        warm = monitor.warm_cache()

    assert grouped_calls == [
        (
            ("https://www.immobilienscout24.de/duesseldorf",),
            ("https://www.immowelt.de/cologne",),
        )
    ]
    assert warm.seen == 2


def test_monitor_activity_log_reports_warm_and_scan(tmp_path: Path, monkeypatch) -> None:
    first = _listing("1", "Warm")
    second = _listing("2", "New")
    batches = [[first], [first, second]]
    messages: list[str] = []

    def fake_scrape(url_groups, limit, headless, real_chrome, concurrent_requests, concurrent_requests_per_domain):
        return [batches.pop(0)]

    monkeypatch.setattr("monitor.scrape_listing_page_groups", fake_scrape)

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immobilienscout24.de/search", "https://www.immowelt.de/classified-search?order=DateDesc"],
            cache=cache,
            notifier=RecordingNotifier(),
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
        price_label=None,
        utilities_eur=None,
        living_area_m2=70.0,
        rooms=2.0,
        provider=None,
        published=None,
        source="Example",
        source_color=0x123456,
        image_url=None,
        google_maps_url="https://www.google.com/maps/search/?api=1&query=Rheinallee+1%2C+D%C3%BCsseldorf",
    )
