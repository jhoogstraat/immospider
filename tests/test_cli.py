from __future__ import annotations

from pathlib import Path

import cli


def test_cli_builds_named_criteria_with_separate_notification_urls(monkeypatch, tmp_path: Path) -> None:
    created_notifiers: list[tuple[str, ...]] = []
    created_monitors: list[dict[str, object]] = []

    class FakeNotifier:
        def __init__(self, urls):
            self.urls = tuple(urls)
            created_notifiers.append(self.urls)

    class FakeCache:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

    class FakeMonitor:
        def __init__(self, urls, **kwargs):
            created_monitors.append({"urls": tuple(urls), **kwargs})

        def run_forever(self, *, interval_seconds, sleep):
            return None

    monkeypatch.setattr(cli, "AppriseNotifier", FakeNotifier)
    monkeypatch.setattr(cli, "SeenListingCache", FakeCache)
    monkeypatch.setattr(cli, "ListingMonitor", FakeMonitor)

    result = cli.main(
        [
            "--monitor",
            "--cache",
            str(tmp_path / "seen.sqlite3"),
            "--criteria",
            "duesseldorf=https://www.immobilienscout24.de/duesseldorf",
            "--criteria",
            "duesseldorf=https://www.immowelt.de/duesseldorf",
            "--criteria",
            "duesseldorf=https://www.kleinanzeigen.de/s-wohnung-mieten/duesseldorf",
            "--criteria-notify-url",
            "duesseldorf=discord://duesseldorf",
            "--criteria",
            "cologne=https://www.immobilienscout24.de/cologne",
            "--criteria-notify-url",
            "cologne=discord://cologne",
        ]
    )

    assert result == 0
    assert created_notifiers == [("discord://duesseldorf",), ("discord://cologne",)]
    monitor = created_monitors[0]
    assert monitor["urls"] == (
        "https://www.immobilienscout24.de/duesseldorf",
        "https://www.immowelt.de/duesseldorf",
        "https://www.kleinanzeigen.de/s-wohnung-mieten/duesseldorf",
        "https://www.immobilienscout24.de/cologne",
    )
    criteria = monitor["criteria"]
    assert [criterion.name for criterion in criteria] == ["duesseldorf", "cologne"]
    assert [criterion.urls for criterion in criteria] == [
        (
            "https://www.immobilienscout24.de/duesseldorf",
            "https://www.immowelt.de/duesseldorf",
            "https://www.kleinanzeigen.de/s-wohnung-mieten/duesseldorf",
        ),
        ("https://www.immobilienscout24.de/cologne",),
    ]
    assert [criterion.notifier.urls for criterion in criteria] == [("discord://duesseldorf",), ("discord://cologne",)]
