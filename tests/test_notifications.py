from __future__ import annotations

from apprise.plugins.discord import NotifyDiscord
from models import Listing
from notifications import _notification_body


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
    assert listing.google_maps_url not in body.splitlines()
    assert "**Published:** 14:05 09.06.2026" in body
    assert "https://www.example.test/expose/123" not in body.splitlines()[1:]
    assert not body.startswith("#")
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

    assert "**[New listing](https://www.example.test/expose/123)**" in body
    assert "**Price:** 980 € cold" in body
    assert "**Published:** Heute, 10:30" in body
