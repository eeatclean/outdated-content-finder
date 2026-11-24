"""Command line: outdated-content-finder https://example.com"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from typing import List, Optional
from urllib.parse import urlsplit

from . import __version__
from .extract import extract
from .fetch import DEFAULT_USER_AGENT, FetchError, Fetcher
from .report import print_table, write_csv, write_json, write_markdown
from .sitemap import PageRef, collect_pages, filter_pages, find_sitemaps, looks_like_sitemap, read_url_list
from .signals import PageScore, score_page


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="outdated-content-finder",
        description=(
            "Rank the pages of a website by how likely they are to contain outdated facts "
            "(past years presented as current, versions, prices, time-relative wording). "
            "It points you to the sentences to check; it does not verify them."
        ),
    )
    parser.add_argument("target", help="A site URL, a sitemap URL, or a local file (sitemap XML or one URL per line)")
    parser.add_argument("--limit", type=int, help="Analyze at most N pages (in sitemap order)")
    parser.add_argument("--include", help="Only analyze URLs matching this regular expression, e.g. '/blog/'")
    parser.add_argument("--exclude", help="Skip URLs matching this regular expression, e.g. '/(tag|category)/'")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (default: 1)")
    parser.add_argument("--timeout", type=float, default=20.0, help="Request timeout in seconds (default: 20)")
    parser.add_argument("--year", type=int, help="Treat this as the current year (default: this year)")
    parser.add_argument("--top", type=int, default=20, help="Rows shown in the terminal and the Markdown report")
    parser.add_argument("--csv", metavar="FILE", help="Write every page and its counts to a CSV file")
    parser.add_argument("--json", metavar="FILE", help="Write every finding to a JSON file")
    parser.add_argument("--markdown", metavar="FILE", help="Write the top pages and their sentences to a Markdown file")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="User agent sent with each request")
    parser.add_argument("--ignore-robots", action="store_true",
                        help="Do not follow robots.txt rules. Use it only on a site you own.")
    parser.add_argument("--quiet", action="store_true", help="Do not print progress")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _log(quiet: bool, message: str) -> None:
    if not quiet:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()


def resolve_pages(target: str, fetcher: Fetcher, quiet: bool) -> List[PageRef]:
    # Warnings are always shown: they explain why a sitemap gave no page.
    warn = lambda message: _log(False, "  " + message)  # noqa: E731
    if os.path.exists(target):
        with open(target, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        if text.lstrip().startswith("<"):
            return collect_pages(target, lambda _url: text if _url == target else fetcher.get(_url), warn)
        return read_url_list(text)
    if not urlsplit(target).scheme:
        target = "https://" + target
    if looks_like_sitemap(target):
        return collect_pages(target, fetcher.get, warn)
    for candidate in find_sitemaps(target, fetcher.robots_sitemaps(target)):
        _log(quiet, f"Reading sitemap {candidate}")
        pages = collect_pages(candidate, fetcher.get, warn)
        if pages:
            return pages
    return []


def analyze(pages: List[PageRef], fetcher: Fetcher, today: date, quiet: bool) -> List[PageScore]:
    scores = []
    for i, ref in enumerate(pages, 1):
        _log(quiet, f"[{i}/{len(pages)}] {ref.url}")
        try:
            html = fetcher.get(ref.url)
        except FetchError as exc:
            scores.append(PageScore(ref.url, "", ref.lastmod, "sitemap", None, [], 0, error=str(exc)))
            continue
        page = extract(ref.url, html)
        scores.append(score_page(page, ref.lastmod, today))
    return scores


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    today = date.today()
    if args.year:
        today = date(args.year, today.month, min(today.day, 28))
    fetcher = Fetcher(args.user_agent, args.delay, args.timeout, respect_robots=not args.ignore_robots)

    pages = resolve_pages(args.target, fetcher, args.quiet)
    found = len(pages)
    pages = filter_pages(pages, args.include, args.exclude, args.limit)
    if not pages:
        _log(False, "No page found. Pass the sitemap URL directly, or a file with one URL per line.")
        return 1
    _log(args.quiet, f"{found} pages found, {len(pages)} to analyze.")

    scores = analyze(pages, fetcher, today, args.quiet)

    print_table(scores, sys.stdout, args.top)
    failed = sum(1 for s in scores if s.error)
    if failed:
        _log(False, f"{failed} page(s) could not be read (see --csv or --json for details).")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            write_csv(scores, handle)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            write_json(scores, handle)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as handle:
            write_markdown(scores, handle, args.top)
    return 0
