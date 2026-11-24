"""Turn an HTML page into a title, dates and the sentences of its main text (standard library only)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional

# Content inside these tags is never part of the article.
SKIP_TAGS = {
    "script", "style", "noscript", "template", "svg", "nav", "header", "footer", "aside", "form",
    "button", "select", "iframe", "canvas",
}
# These tags start a new block of text, so a sentence never runs across them.
BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "br",
    "section", "article", "main", "blockquote", "pre", "figcaption", "dd", "dt", "table",
}
VOID_TAGS = {"br", "img", "hr", "meta", "link", "input", "source", "wbr", "area", "base", "col", "embed"}
# Classes and ids that usually hold comments, menus or related posts rather than the article.
NOISE_ATTR = re.compile(
    r"(^|[\s_-])(comments?|sidebar|related|share|sharing|social|breadcrumbs?|menu|newsletter|cookie|"
    r"footer|header|nav|widget|advert|ads?|promo|subscribe|author-bio)([\s_-]|$)",
    re.I,
)
DATE_META = {
    "article:modified_time": "modified",
    "og:updated_time": "modified",
    "last-modified": "modified",
    "dc.date.modified": "modified",
    "article:published_time": "published",
    "datepublished": "published",
    "dc.date": "published",
    "date": "published",
}


@dataclass
class Page:
    url: str
    title: str = ""
    h1: str = ""
    published: str = ""
    modified: str = ""
    sentences: List[str] = field(default_factory=list)
    word_count: int = 0


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[str] = []
        self.skip_depth = 0
        self.noise_depth = 0
        self.in_title = False
        self.in_h1 = False
        self.in_ld_json = False
        self.title = ""
        self.h1 = ""
        self.meta: Dict[str, str] = {}
        self.ld_json: List[str] = []
        self.times: List[str] = []
        # Text collected for the whole body, inside <main> and inside <article>.
        self.buffers: Dict[str, List[str]] = {"body": [], "main": [], "article": []}
        self.open_regions: Dict[str, int] = {"main": 0, "article": 0}

    def _write(self, text: str) -> None:
        if self.skip_depth or self.noise_depth:
            return
        self.buffers["body"].append(text)
        for region, depth in self.open_regions.items():
            if depth:
                self.buffers[region].append(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
            if key and attrs.get("content"):
                self.meta.setdefault(key, attrs["content"])
            return
        if tag == "time" and attrs.get("datetime"):
            self.times.append(attrs["datetime"])
        if tag == "script" and (attrs.get("type") or "").lower() == "application/ld+json":
            self.in_ld_json = True
        if tag == "title":
            self.in_title = True
        if tag == "h1":
            self.in_h1 = True
        if tag in VOID_TAGS:
            if tag == "br":
                self._write("\n")
            return
        self.stack.append(tag)
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        marker = f"{attrs.get('class') or ''} {attrs.get('id') or ''}"
        if self.noise_depth or (tag in {"div", "section", "ul", "ol"} and NOISE_ATTR.search(marker)):
            self.noise_depth += 1
            self.stack[-1] = tag + "#noise"
        if tag in self.open_regions:
            self.open_regions[tag] += 1
        if tag in BLOCK_TAGS:
            self._write("\n")

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if tag == "title":
            self.in_title = False
        if tag == "h1":
            self.in_h1 = False
        if tag == "script":
            self.in_ld_json = False
        # Close up to the matching tag, so badly nested HTML cannot leave a region open forever.
        if not any(t.split("#")[0] == tag for t in self.stack):
            return
        while self.stack:
            current = self.stack.pop()
            name = current.split("#")[0]
            if current.endswith("#noise"):
                self.noise_depth -= 1
            if name in SKIP_TAGS:
                self.skip_depth -= 1
            if name in self.open_regions:
                self.open_regions[name] -= 1
            if name in BLOCK_TAGS:
                self._write("\n")
            if name == tag:
                break

    def handle_data(self, data):
        if self.in_ld_json:
            self.ld_json.append(data)
            return
        if self.in_title:
            self.title += data
        if self.in_h1:
            self.h1 += data
        self._write(data)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _iso_date(value: str) -> str:
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value or "")
    return match.group(0) if match else ""


def _dates_from_ld_json(blocks: List[str]):
    published = modified = ""

    def walk(node):
        nonlocal published, modified
        if isinstance(node, dict):
            if not modified and node.get("dateModified"):
                modified = _iso_date(str(node["dateModified"]))
            if not published and node.get("datePublished"):
                published = _iso_date(str(node["datePublished"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for block in blocks:
        try:
            walk(json.loads(block))
        except ValueError:
            continue
    return published, modified


SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9\"“«¿¡(])")


def split_sentences(text: str) -> List[str]:
    sentences = []
    for block in text.split("\n"):
        block = _clean(block)
        if not block:
            continue
        for sentence in SENTENCE_END.split(block):
            sentence = sentence.strip()
            if len(sentence) >= 3:
                sentences.append(sentence)
    return sentences


def extract(url: str, html: str, min_region_words: int = 150) -> Page:
    parser = _Parser()
    parser.feed(html)
    parser.close()

    chosen = "body"
    for region in ("article", "main"):
        words = len("".join(parser.buffers[region]).split())
        if words >= min_region_words:
            chosen = region
            break
    text = "".join(parser.buffers[chosen])

    meta_published = meta_modified = ""
    for key, kind in DATE_META.items():
        value = _iso_date(parser.meta.get(key, ""))
        if value and kind == "modified" and not meta_modified:
            meta_modified = value
        if value and kind == "published" and not meta_published:
            meta_published = value
    ld_published, ld_modified = _dates_from_ld_json(parser.ld_json)
    time_dates = sorted(d for d in (_iso_date(t) for t in parser.times) if d)

    title = _clean(parser.meta.get("og:title") or parser.title)
    sentences = split_sentences(text)
    return Page(
        url=url,
        title=title,
        h1=_clean(parser.h1),
        published=meta_published or ld_published or (time_dates[0] if time_dates else ""),
        modified=meta_modified or ld_modified or (time_dates[-1] if len(time_dates) > 1 else ""),
        sentences=sentences,
        word_count=len(text.split()),
    )


def best_date(page: Page, sitemap_lastmod: str = "") -> tuple:
    """The most trustworthy 'last changed' date and where it came from."""
    if page.modified:
        return page.modified, "page"
    lastmod = _iso_date(sitemap_lastmod)
    if lastmod:
        return lastmod, "sitemap"
    if page.published:
        return page.published, "published"
    return "", ""


def first_non_empty(*values: Optional[str]) -> str:
    return next((v for v in values if v), "")
