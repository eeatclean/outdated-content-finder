"""Polite HTTP fetching: one user agent, a delay between requests and robots.txt rules."""

from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.request
import urllib.robotparser
from typing import Dict, Optional
from urllib.parse import urlsplit

from . import __version__

DEFAULT_USER_AGENT = f"outdated-content-finder/{__version__} (open-source content audit script)"


class FetchError(Exception):
    """Raised when a page cannot be downloaded."""


class Fetcher:
    """Downloads pages one at a time and waits between requests."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        delay: float = 1.0,
        timeout: float = 20.0,
        respect_robots: bool = True,
    ) -> None:
        self.user_agent = user_agent
        self.delay = delay
        self.timeout = timeout
        self.respect_robots = respect_robots
        self._robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self._last_request = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.monotonic()

    def _robots_for(self, url: str) -> Optional[urllib.robotparser.RobotFileParser]:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                text = self._download(origin + "/robots.txt")
                parser.parse(text.splitlines())
                self._robots[origin] = parser
            except FetchError:
                # No readable robots.txt: everything is allowed.
                self._robots[origin] = None
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parser = self._robots_for(url)
        return parser is None or parser.can_fetch(self.user_agent, url)

    def robots_sitemaps(self, url: str) -> list:
        """Sitemap URLs declared in the robots.txt of the site that hosts ``url``."""
        parser = self._robots_for(url) if self.respect_robots else None
        if parser is None:
            parts = urlsplit(url)
            try:
                text = self._download(f"{parts.scheme}://{parts.netloc}/robots.txt")
            except FetchError:
                return []
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(text.splitlines())
        return list(parser.site_maps() or [])

    def _download(self, url: str) -> str:
        self._wait()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = response.read()
                encoding = response.headers.get("Content-Encoding", "")
                charset = response.headers.get_content_charset() or "utf-8"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise FetchError(f"{url}: {exc}") from exc
        if encoding == "gzip" or url.endswith(".gz") or data[:2] == b"\x1f\x8b":
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
        return data.decode(charset, errors="replace")

    def get(self, url: str) -> str:
        if not self.allowed(url):
            raise FetchError(f"{url}: blocked by robots.txt")
        return self._download(url)
