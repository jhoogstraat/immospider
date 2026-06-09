from __future__ import annotations
from datetime import UTC, datetime


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
    return listing.source


def _notification_body(listing: Listing) -> str:
    title = _markdown_link(listing.title or "New listing", listing.url)
    lines = [f"**{title}**"]

    price = _format_price(listing.price_eur, listing.price_label)
    if price is not None:
        lines.append(f"**Price:** {price}")
    utilities = _format_price(listing.utilities_eur, None)
    if utilities is not None:
        lines.append(f"**Utilities / Nebenkosten:** {utilities}")

    details = [
        ("Size", _format_area(listing.living_area_m2)),
        ("Rooms", _format_rooms(listing.rooms)),
        ("Address", _format_address(listing.address, listing.google_maps_url)),
        ("Provider", listing.provider),
        ("Published", _format_published(listing.published)),
        ("Source", listing.source),
    ]
    lines.extend(f"**{name}:** {value}" for name, value in details if value)
    if listing.image_url:
        lines.append(f"**Image:** {_markdown_link('Open image', listing.image_url)}")
    return "\n".join(lines)


def _format_price(value: float | None, label: str | None) -> str | None:
    if value is None:
        return None
    formatted = f"{value:,.0f} €".replace(",", ".")
    if label == "warm":
        return f"{formatted} warm"
    if label == "cold":
        return f"{formatted} cold"
    return formatted


def _format_area(value: float | None) -> str | None:
    return f"{value:g} m²" if value is not None else None


def _format_rooms(value: float | None) -> str | None:
    return f"{value:g}" if value is not None else None

def _format_address(address: str | None, google_maps_url: str | None) -> str | None:
    if address is None:
        return None
    return _markdown_link(address, google_maps_url) if google_maps_url else address


def _format_published(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    parsed = _parse_datetime(normalized)
    if parsed is None:
        return normalized
    return parsed.astimezone().strftime("%H:%M %d.%m.%Y")


def _parse_datetime(value: str) -> datetime | None:
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _markdown_link(text: str, url: str) -> str:
    return f"[{_escape_markdown_link_text(text)}]({url})"


def _escape_markdown_link_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
