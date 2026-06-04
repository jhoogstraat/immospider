from __future__ import annotations

import argparse
import json
from datetime import datetime
import sys
from pathlib import Path

from .cache import DEFAULT_CACHE_PATH, SeenListingCache
from .monitor import ListingMonitor
from .notifications import AppriseNotifier

from .pages import DEFAULT_URLS
from .scraper import DEFAULT_CONCURRENT_REQUESTS, DEFAULT_CONCURRENT_REQUESTS_PER_DOMAIN, listing_dicts, scrape_listing_pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="listing-scraper",
        description="Scrape latest property listings from configured search URLs with Scrapling.",
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="Search URL to scrape. Repeat to scrape multiple pages. Defaults to the built-in pages.",
    )
    parser.add_argument("--limit", type=_positive_int, default=20, help="Maximum listings to fetch per scan.")
    parser.add_argument("--output", type=Path, help="Write one-shot JSON output to this path instead of stdout.")
    parser.add_argument("--headful", action="store_true", help="Run browser visibly for manual anti-bot challenges.")
    parser.add_argument("--real-chrome", action="store_true", help="Use installed Google Chrome instead of bundled Chromium.")
    parser.add_argument("--solve-cloudflare", action="store_true", help="Try Scrapling's Cloudflare challenge solver when a page is actually challenged.")
    parser.add_argument("--monitor", action="store_true", help="Continuously scan, warming the cache before notifications.")
    parser.add_argument("--notify-url", action="append", dest="notify_urls", help="Apprise notification URL. Repeat for multiple endpoints.")
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

    urls = args.urls if args.urls is not None else DEFAULT_URLS
    if args.monitor:
        if not args.notify_urls:
            parser.error("--monitor requires at least one --notify-url")
        notifier = AppriseNotifier(args.notify_urls)
        with SeenListingCache(args.cache) as cache:
            monitor = ListingMonitor(
                urls,
                cache=cache,
                notifier=notifier,
                limit=args.limit,
                headless=not args.headful,
                real_chrome=args.real_chrome,
                solve_cloudflare=args.solve_cloudflare,
                concurrent_requests=args.concurrency,
                concurrent_requests_per_domain=args.per_domain_concurrency,
                activity_log=_activity_log,
            )
            monitor.run_forever(interval_seconds=args.interval)
        return 0

    listings = scrape_listing_pages(
        urls,
        limit=args.limit,
        headless=not args.headful,
        real_chrome=args.real_chrome,
        solve_cloudflare=args.solve_cloudflare,
        concurrent_requests=args.concurrency,
        concurrent_requests_per_domain=args.per_domain_concurrency,
    )
    payload = json.dumps(listing_dicts(listings), ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")
    return 0


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
