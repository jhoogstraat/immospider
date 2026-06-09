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


class FailingNotifier:
    def notify(self, listing: Listing) -> bool:
        raise RuntimeError("discord rejected payload")


def test_first_monitor_fetch_warms_cache_without_notifications(tmp_path: Path, monkeypatch) -> None:
    first = _listing("1", "Warm")
    second = _listing("2", "New")
    batches = [[first], [first, second]]
    notifier = RecordingNotifier()

    def fake_scrape(url_groups, limit, headless, real_chrome, concurrent_requests, concurrent_requests_per_domain, activity_log=None):
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

def test_monitor_logs_notification_errors_without_crashing(tmp_path: Path) -> None:
    messages: list[str] = []
    listing = _listing("1", "New")

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immobilienscout24.de/search"],
            cache=cache,
            notifier=FailingNotifier(),
            activity_log=messages.append,
        )

        scan = monitor._scan_with_listings([[listing]])

    assert scan.seen == 1
    assert scan.new == 1
    assert scan.notified == 0
    assert messages == [
        "notification failed for https://www.example.test/expose/1: discord rejected payload",
        "scan complete: seen=1 new=1 notified=0",
    ]


def test_monitor_run_forever_warms_before_first_scan(tmp_path: Path, monkeypatch) -> None:
    warm_listing = _listing("1", "Warm")
    new_listing = _listing("2", "New")
    notifier = RecordingNotifier()
    batches = [[[warm_listing]], [[warm_listing, new_listing]]]

    def fake_scrape(url_groups, limit, headless, real_chrome, concurrent_requests, concurrent_requests_per_domain, activity_log=None):
        assert tuple(url_groups) == (("https://www.immowelt.de/classified-search?order=DateDesc",),)
        return batches.pop(0)

    monkeypatch.setattr("monitor.scrape_listing_page_groups", fake_scrape)
    monkeypatch.setattr("monitor.sleep", lambda seconds: None)

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immowelt.de/classified-search?order=DateDesc"],
            cache=cache,
            notifier=notifier,
        )

        monitor.run_forever(interval_seconds=1, max_scans=1)

    assert notifier.sent == [new_listing]


def test_monitor_run_forever_scans_until_max_scans(tmp_path: Path, monkeypatch) -> None:
    listings = [_listing("1", "Warm"), _listing("2", "First"), _listing("3", "Second")]
    notifier = RecordingNotifier()
    batches = [[[listings[0]]], [[listings[0], listings[1]]], [[listings[0], listings[2]]]]

    def fake_scrape(url_groups, limit, headless, real_chrome, concurrent_requests, concurrent_requests_per_domain, activity_log=None):
        return batches.pop(0)

    monkeypatch.setattr("monitor.scrape_listing_page_groups", fake_scrape)
    monkeypatch.setattr("monitor.sleep", lambda seconds: None)

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immowelt.de/classified-search?order=DateDesc"],
            cache=cache,
            notifier=notifier,
        )

        monitor.run_forever(interval_seconds=1, max_scans=2)

    assert batches == []
    assert notifier.sent == listings[1:]


def test_monitor_run_forever_continues_after_scrape_error(tmp_path: Path, monkeypatch) -> None:
    listing = _listing("1", "Recovered")
    notifier = RecordingNotifier()
    calls = 0
    messages: list[str] = []

    def fake_scrape(url_groups, limit, headless, real_chrome, concurrent_requests, concurrent_requests_per_domain, activity_log=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("browser timed out")
        return [[listing]]

    monkeypatch.setattr("monitor.scrape_listing_page_groups", fake_scrape)
    monkeypatch.setattr("monitor.sleep", lambda seconds: None)

    with SeenListingCache(tmp_path / "seen.sqlite3") as cache:
        monitor = ListingMonitor(
            ["https://www.immowelt.de/classified-search?order=DateDesc"],
            cache=cache,
            notifier=notifier,
            activity_log=messages.append,
        )

        monitor.run_forever(interval_seconds=1, max_scans=1)

    assert notifier.sent == [listing]
    assert messages == [
        "warming cache: fetching 1 page(s)",
        "cache warm failed: browser timed out",
        "cache warm: seen=0 cached_new=0 notified=0",
        "scan starting: fetching 1 page(s)",
        "scan complete: seen=1 new=1 notified=1",
    ]

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

    def fake_scrape(url_groups, limit, headless, real_chrome, concurrent_requests, concurrent_requests_per_domain, activity_log=None):
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

    def fake_scrape(url_groups, limit, headless, real_chrome, concurrent_requests, concurrent_requests_per_domain, activity_log=None):
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
