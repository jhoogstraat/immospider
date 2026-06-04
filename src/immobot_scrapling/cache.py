from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Listing

DEFAULT_CACHE_PATH = Path(".immobot_scrapling.sqlite3")


class SeenListingCache:
    def __init__(self, path: Path | str = DEFAULT_CACHE_PATH) -> None:
        self.path = Path(path)
        self._connection: sqlite3.Connection | None = None

    def __enter__(self) -> SeenListingCache:
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def open(self) -> None:
        if self._connection is not None:
            return
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_listings (
                cache_key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                listing_id TEXT,
                url TEXT NOT NULL,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._connection = connection

    def close(self) -> None:
        if self._connection is None:
            return
        self._connection.close()
        self._connection = None

    def contains(self, listing: Listing) -> bool:
        connection = self._require_connection()
        row = connection.execute(
            "SELECT 1 FROM seen_listings WHERE cache_key = ?",
            (_cache_key(listing),),
        ).fetchone()
        return row is not None

    def remember(self, listing: Listing) -> bool:
        return self.add_if_new(listing)

    def remember_many(self, listings: list[Listing]) -> int:
        inserted = 0
        for listing in listings:
            if self.add_if_new(listing):
                inserted += 1
        return inserted

    def add_if_new(self, listing: Listing) -> bool:
        connection = self._require_connection()
        cursor = connection.execute(
            """
            INSERT INTO seen_listings (cache_key, source, listing_id, url)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cache_key) DO NOTHING
            """,
            (_cache_key(listing), listing.source, listing.id, listing.url),
        )
        inserted = cursor.rowcount == 1
        if not inserted:
            connection.execute(
                "UPDATE seen_listings SET last_seen_at = CURRENT_TIMESTAMP WHERE cache_key = ?",
                (_cache_key(listing),),
            )
        connection.commit()
        return inserted


    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self.open()
        if self._connection is None:
            raise RuntimeError("cache connection is not open")
        return self._connection


def _cache_key(listing: Listing) -> str:
    return f"{listing.source}:{listing.id}" if listing.id is not None else listing.url
