from __future__ import annotations

import argparse
import signal
from datetime import datetime
import sys
import threading
from pathlib import Path

from cache import DEFAULT_CACHE_PATH, SeenListingCache
from monitor import ListingMonitor, SearchCriteria
from notifications import AppriseNotifier

from scraper import DEFAULT_CONCURRENT_REQUESTS, DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="listing-scraper",
        description="Scrape latest property listings from configured search URLs with Scrapling.",
    )
    parser.add_argument(
        "--criteria",
        action="append",
        dest="criteria",
        metavar="NAME=URL",
        help=(
            "Named search criteria to scrape. Repeat with the same NAME to include multiple domain search URLs "
            "in one notification channel."
        ),
    )
    parser.add_argument("--limit", type=_positive_int, default=20, help="Maximum listings to fetch per scan.")
    parser.add_argument("--headful", action="store_true", help="Run browser visibly for manual anti-bot challenges.")
    parser.add_argument("--real-chrome", action="store_true", help="Use installed Google Chrome instead of bundled Chromium.")
    parser.add_argument("--notify-url", action="append", dest="notify_urls", help="Apprise notification URL. Repeat for multiple endpoints.")
    parser.add_argument(
        "--criteria-notify-url",
        action="append",
        dest="criteria_notify_urls",
        metavar="NAME=APPRISE_URL",
        help="Apprise notification URL for a named --criteria channel. Repeat for multiple endpoints.",
    )
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_PATH, help="SQLite cache path for seen listings.")
    parser.add_argument("--interval", type=_positive_float, default=60.0, help="Seconds between monitor scans.")
    parser.add_argument("--concurrency", type=_positive_int, default=DEFAULT_CONCURRENT_REQUESTS, help="Maximum listing pages fetched at the same time.")
    parser.add_argument(
        "--per-domain-concurrency",
        type=_non_negative_int,
        default=DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN,
        help="Maximum concurrent listing page fetches per domain. Use 0 for no per-domain limit.",
    )
    args = parser.parse_args(argv)

    criteria_urls = _group_keyed_values(args.criteria or [], "--criteria", parser)
    if args.criteria_notify_urls and not criteria_urls:
        parser.error("--criteria-notify-url requires --criteria")
    if not criteria_urls:
        parser.error("at least one --criteria NAME=URL is required")
    urls = tuple(url for criterion_urls in criteria_urls.values() for url in criterion_urls)
    criteria_notify_urls = _group_keyed_values(args.criteria_notify_urls or [], "--criteria-notify-url", parser)
    fallback_notify_urls = tuple(args.notify_urls or ())
    missing = [name for name in criteria_urls if name not in criteria_notify_urls and not fallback_notify_urls]
    if missing:
        parser.error(
            "--criteria requires --criteria-notify-url NAME=URL or --notify-url for: "
            + ", ".join(missing)
        )
    criteria = tuple(
        SearchCriteria(
            name,
            tuple(criteria_urls[name]),
            AppriseNotifier([*criteria_notify_urls.get(name, ()), *fallback_notify_urls]),
        )
        for name in criteria_urls
    )
    notifier = criteria[0].notifier
    with SeenListingCache(args.cache) as cache:
        monitor = ListingMonitor(
            urls,
            cache=cache,
            notifier=notifier,
            criteria=criteria,
            limit=args.limit,
            headless=not args.headful,
            real_chrome=args.real_chrome,
            concurrent_requests=args.concurrency,
            concurrent_requests_per_domain=args.per_domain_concurrency,
            activity_log=_activity_log,
        )
        stop_requested = threading.Event()
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        def request_stop(signum: int, frame: object) -> None:
            if not stop_requested.is_set():
                _activity_log("stop requested; finishing current scan")
                stop_requested.set()

        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)
        try:
            monitor.run_forever(interval_seconds=args.interval, sleep=stop_requested.wait)
        finally:
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)
        if stop_requested.is_set():
            _activity_log("monitor stopped")
            return 130
    return 0


def _group_keyed_values(values: list[str], option: str, parser: argparse.ArgumentParser) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for value in values:
        name, separator, item = value.partition("=")
        if not separator or not name or not item:
            parser.error(f"{option} must use NAME=VALUE")
        grouped.setdefault(name, []).append(item)
    return grouped


def _activity_log(message: str) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
