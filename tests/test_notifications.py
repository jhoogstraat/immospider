from __future__ import annotations

import sys

from apprise.plugins.discord import NotifyDiscord
from models import Listing
from notifications import AppriseNotifier, _notification_body, _notification_title


def test_notification_body_formats_listing_links_price_and_timestamp() -> None:
    listing = Listing(
        id="123",
        title="Bright [Altbau]",
        url="https://www.example.test/expose/123",
        address="Rheinallee 1, Düsseldorf",
        price_eur=1250.0,
        price_label="warm",
        utilities_eur=180.0,
        living_area_m2=72.5,
        rooms=2.5,
        provider="Beispiel Immobilien",
        published="2026-06-09T14:05:00+02:00",
        source="Example",
        source_color=0x123456,
        image_url="https://www.example.test/image.jpg",
        google_maps_url="https://www.google.com/maps/search/?api=1&query=Rheinallee+1%2C+D%C3%BCsseldorf",
    )

    body = _notification_body(listing)

    assert "**[Bright \\[Altbau\\]](https://www.example.test/expose/123)**" in body
    assert "**Price:** 1.250 € warm" in body
    assert "**Utilities / Nebenkosten:** 180 €" in body
    assert "**Address:** [Rheinallee 1, Düsseldorf](https://www.google.com/maps/search/?api=1&query=Rheinallee+1%2C+D%C3%BCsseldorf)" in body
    assert "**Google Maps:**" not in body
    assert body.count("Example") == 1
    assert listing.google_maps_url not in body.splitlines()
    assert "**Published:** 09.06.2026 14:05" in body
    assert "https://www.example.test/expose/123" not in body.splitlines()[1:]
    assert not body.startswith("#")
    assert "**Image:** image" in body
    assert listing.image_url not in body
    assert _notification_title(listing) == ""
    description, fields = NotifyDiscord.extract_markdown_sections(body)
    assert description == body
    assert fields == []

def test_notification_body_keeps_unparsed_published_text() -> None:
    listing = Listing(
        id="123",
        title=None,
        url="https://www.example.test/expose/123",
        address=None,
        price_eur=980.0,
        price_label="cold",
        utilities_eur=None,
        living_area_m2=None,
        rooms=None,
        provider=None,
        published="Heute, 10:30",
        source="Example",
        source_color=0x123456,
        image_url=None,
        google_maps_url=None,
    )

    body = _notification_body(listing)

    assert "**[https://www.example.test/expose/123](https://www.example.test/expose/123)**" in body
    assert "**Price:** 980 € cold" in body
    assert "**Published:** Heute, 10:30" in body

def test_apprise_notifier_attaches_listing_image(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeApprise:
        def add(self, url: str) -> None:
            assert url == "discord://example"

        def notify(self, **kwargs: object) -> bool:
            calls.append(kwargs)
            return True

    class FakeAppriseModule:
        Apprise = FakeApprise

    monkeypatch.setitem(sys.modules, "apprise", FakeAppriseModule)
    listing = Listing(
        id="123",
        title="Bright Altbau",
        url="https://www.example.test/expose/123",
        address=None,
        price_eur=None,
        price_label=None,
        utilities_eur=None,
        living_area_m2=None,
        rooms=None,
        provider=None,
        published=None,
        source="Example",
        source_color=0x123456,
        image_url="https://www.example.test/image.jpg",
        google_maps_url=None,
    )

    assert AppriseNotifier(["discord://example"]).notify(listing)

    assert calls == [
        {
            "title": "",
            "body": _notification_body(listing),
            "body_format": "markdown",
            "attach": [listing.image_url],
        }
    ]