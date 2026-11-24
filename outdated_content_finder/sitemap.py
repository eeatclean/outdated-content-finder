"""Read every page URL from a sitemap, a sitemap index or a plain list of URLs."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Set
from urllib.parse import urljoin, urlsplit

SKIPPED_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif", ".pdf", ".zip",
    ".mp4", ".mp3", ".webm", ".css", ".js", ".json", ".xml", ".txt",
)
COMMON_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml", "/sitemap-index.xml")


@dataclass
class PageRef:
    url: str
    lastmod: str = ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap(text: str):
    """Return ``(kind, entries)`` where kind is ``index`` or ``urlset``.

    For an index, entries are child sitemap URLs. For a urlset, entries are ``PageRef`` objects.
    """
    text = text.lstrip("﻿ \r\n\t")
    root = ET.fromstring(text.encode("utf-8"))
    kind = _local(root.tag)
    if kind == "sitemapindex":
        children = []
        for node in root:
            if _local(node.tag) == "sitemap":
                loc = next((c.text for c in node if _local(c.tag) == "loc" and c.text), None)
                if loc:
                    children.append(loc.strip())
        return "index", children
    pages = []
    for node in root:
        if _local(node.tag) != "url":
            continue
        loc = lastmod = ""
        for child in node:
            name = _local(child.tag)
            if name == "loc" and child.text:
                loc = child.text.strip()
            elif name == "lastmod" and child.text:
                lastmod = child.text.strip()
        if loc:
            pages.append(PageRef(loc, lastmod))
    return "urlset", pages


def is_probably_html(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return not path.endswith(SKIPPED_EXTENSIONS)


def collect_pages(
    start: str,
    get: Callable[[str], str],
    warn: Callable[[str], None] = lambda message: None,
    max_sitemaps: int = 500,
) -> List[PageRef]:
    """Follow a sitemap (and nested sitemap indexes) and return every page it lists."""
    seen: Set[str] = set()
    queue = [start]
    pages: List[PageRef] = []
    known: Set[str] = set()
    while queue and len(seen) < max_sitemaps:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            kind, entries = parse_sitemap(get(url))
        except ET.ParseError as exc:
            warn(f"Skipped {url}: not a valid sitemap ({exc})")
            continue
        except Exception as exc:  # network errors are reported, not fatal
            warn(f"Skipped {url}: {exc}")
            continue
        if kind == "index":
            queue.extend(urljoin(url, child) for child in entries)
            continue
        for page in entries:
            page.url = urljoin(url, page.url)
            if page.url not in known and is_probably_html(page.url):
                known.add(page.url)
                pages.append(page)
    return pages


def find_sitemaps(site_url: str, robots_sitemaps: Iterable[str]) -> List[str]:
    """Candidate sitemap URLs for a site: those declared in robots.txt first, then common paths."""
    parts = urlsplit(site_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    found = [u for u in robots_sitemaps if u]
    return found or [origin + path for path in COMMON_SITEMAP_PATHS]


def looks_like_sitemap(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith((".xml", ".xml.gz")) or "sitemap" in path


def read_url_list(text: str) -> List[PageRef]:
    """One URL per line; blank lines and lines starting with # are ignored."""
    pages = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and re.match(r"https?://", line):
            pages.append(PageRef(line))
    return pages


def filter_pages(
    pages: List[PageRef],
    include: Optional[str] = None,
    exclude: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[PageRef]:
    if include:
        pattern = re.compile(include)
        pages = [p for p in pages if pattern.search(p.url)]
    if exclude:
        pattern = re.compile(exclude)
        pages = [p for p in pages if not pattern.search(p.url)]
    if limit is not None:
        pages = pages[:limit]
    return pages
