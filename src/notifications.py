from __future__ import annotations

from typing import Protocol

from models import Listing


class Notifier(Protocol):
    def notify(self, listing: Listing) -> bool: ...


class AppriseNotifier:
    def __init__(self, urls: list[str] | tuple[str, ...]) -> None:
        if not urls:
            raise ValueError("at least one notification URL is required")
        try:
            import apprise
        except ImportError as exc:
            raise RuntimeError("Apprise is required for notifications; install the project dependencies") from exc
        self._apprise = apprise.Apprise()
        for url in urls:
            self._apprise.add(url)

    def notify(self, listing: Listing) -> bool:
        return bool(
            self._apprise.notify(
                title=_notification_title(listing),
                body=_notification_body(listing),
                body_format="markdown",
            )
        )


def _notification_title(listing: Listing) -> str:
    title = listing.title or "New listing"
    return f"{listing.source}: {title}"


def _notification_body(listing: Listing) -> str:
    fields = [
        ("Price", _format_price(listing.price_eur)),
        ("Size", _format_area(listing.living_area_m2)),
        ("Rooms", _format_rooms(listing.rooms)),
        ("Address", listing.address),
        ("Provider", listing.provider),
        ("Published", listing.published),
        ("Source", listing.source),
    ]
    lines = [f"**{name}:** {value}" for name, value in fields if value]
    if listing.image_url:
        lines.append(f"**Image:** {listing.image_url}")
    if listing.google_maps_url:
        lines.append(f"**Google Maps:** {listing.google_maps_url}")
    lines.append(f"**Listing:** {listing.url}")
    return "\n".join(lines)


def _format_price(value: float | None) -> str | None:
    return f"{value:,.0f} €".replace(",", ".") if value is not None else None


def _format_area(value: float | None) -> str | None:
    return f"{value:g} m²" if value is not None else None


def _format_rooms(value: float | None) -> str | None:
    return f"{value:g}" if value is not None else None
