"""Spot the sentences that are most likely to go out of date.

The rules are deliberately simple and readable. They do not decide whether a sentence is wrong:
they point to the sentences worth checking against an official source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

# Kinds of signals, their weight in the page score and a plain-language label.
KINDS: Dict[str, tuple] = {
    "year_in_title": (3, "Past year in the title"),
    "past_year_as_current": (3, "Past year presented as current"),
    "future_in_past": (3, "Future event dated in a past year"),
    "version": (2, "Version or model number"),
    "price": (2, "Price or plan"),
    "time_relative": (1, "Time-relative wording"),
    "dated": (1, "Dated reference"),
}

# A year stands alone: not inside a date like 2023-05-01, a decimal, or a phone number like 0800 2023 456.
YEAR = re.compile(r"(?<![\d/.,-])(?<!\d )(20\d{2})(?![\d/.,-]?\d)(?! \d{2,})")

# Words that present something as true now ("the best tools of 2023", "currently costs").
CURRENT_CUES = re.compile(
    r"\b(currently|as of|latest|newest|nowadays|right now|today|this year|at the moment|best|up[- ]to[- ]date|"
    r"actuellement|aujourd'hui|aujourd’hui|en ce moment|cette année|meilleure?s?|désormais|à ce jour|"
    r"la dernière version|le dernier modèle|"
    r"actualmente|hoy|ahora|este año|mejores?|la última versión|el último modelo|"
    r"aktuell|derzeit|heute|jetzt|dieses jahr|beste[nrs]?|neueste[nrs]?)\b",
    re.I,
)
# Words that announce an event to come ("will launch in 2024").
FUTURE_CUES = re.compile(
    r"\b(will|won't|upcoming|coming soon|expected|scheduled|planned|plans to|is set to|is due|"
    r"sera|seront|va|vont|prochainement|à venir|prévue?s?|devrait|devraient|"
    r"será|serán|va a|van a|próximamente|previsto|prevista|"
    r"wird|werden|geplant|demnächst|voraussichtlich)\b",
    re.I,
)
# Words that place a year in history, where it is expected to stay the same.
HISTORY_CUES = re.compile(
    r"\b(founded|since|launched|created|introduced|established|born|history|historically|"
    r"released|announced|written|wrote|published|acquired|rebranded|renamed|discontinued|originally|in the past|back in|ago|"
    r"fondée?|depuis|lancée?|créée?|née?|annoncée?|écrite?s?|publiée?s?|rachetée?|histoire|à l'époque|à l’époque|"
    r"fundad[oa]|desde|lanzad[oa]|cread[oa]|anunciad[oa]|escrit[oa]|publicad[oa]|historia|"
    r"gegründet|seit|eingeführt|angekündigt|geschrieben|veröffentlicht|geschichte|damals)\b",
    re.I,
)
# Wording that silently depends on the day the article was written.
TIME_RELATIVE = re.compile(
    r"\b(currently|as of now|at the moment|at the time of writing|right now|nowadays|this year|"
    r"last year|next year|recently|the latest version|the newest version|"
    r"actuellement|en ce moment|à l'heure actuelle|à l’heure actuelle|au moment d'écrire|"
    r"au moment où nous écrivons|cette année|l'année dernière|l’année dernière|l'an prochain|"
    r"l’an prochain|récemment|à ce jour|la dernière version|"
    r"actualmente|en este momento|este año|el año pasado|el próximo año|recientemente|la última versión|"
    r"derzeit|momentan|zurzeit|dieses jahr|letztes jahr|nächstes jahr|kürzlich|die neueste version)\b",
    re.I,
)

VERSION_EXPLICIT = re.compile(
    r"\b(?:version|versión|versione|ver\.)\s?\d+(?:\.\d+)*\b|\bv\d+(?:\.\d+)+\b|\bv\d{1,2}\b",
    re.I,
)
VERSION_NAMED = re.compile(
    r"\b(?:iOS|iPadOS|macOS|watchOS|Android|Windows(?: Server)?|Ubuntu|Debian|Fedora|PHP|Python|"
    r"Node(?:\.js)?|Java|JDK|Chrome|Firefox|Safari|WordPress|Drupal|Joomla|Laravel|Django|React|"
    r"Angular|Vue|Kotlin|Swift|Ruby|Rails|\.NET|Excel|Office|Photoshop|iPhone|Galaxy S|Pixel|"
    r"PlayStation|Xbox|Bluetooth|Wi-?Fi|USB|HDMI|PCIe|DDR|GPT|Gemini|Claude|Llama)[ -]?\d+(?:\.\d+)*\b"
)
VERSION_DOTTED = re.compile(r"\b([A-Z][A-Za-z0-9+#-]{1,24}) (\d+\.\d+(?:\.\d+)?)\b(?!\s?(?:%|stars?|/5|out of))")
NOT_PRODUCTS = {
    "Rated", "Rating", "Score", "Page", "Step", "Figure", "Fig", "Table", "Chapter", "Section", "Top",
    "Level", "Grade", "Note", "Chart", "Part", "Article", "Appendix", "Item", "Volume", "Vol", "Only",
    "About", "Around", "Over", "Under", "Nearly", "Almost", "Approximately", "Just", "Up", "From",
    "Étape", "Chapitre", "Partie", "Paso", "Capítulo", "Schritt", "Kapitel", "Teil",
}
PRICE = re.compile(
    r"(?:[$€£¥]\s?\d[\d.,]*|\b\d[\d.,]*\s?(?:€|\$|£|USD|EUR|GBP|CHF|CAD|AUD|dollars?|euros?)(?!\w))"
)
# Plan names that change often even without a visible amount.
PLAN = re.compile(r"\b(free plan|free tier|offre gratuite|plan gratuito|kostenloser tarif)\b", re.I)


@dataclass
class Finding:
    kind: str
    sentence: str
    detail: str = ""
    extra: int = 0

    @property
    def weight(self) -> int:
        return KINDS[self.kind][0] + self.extra

    @property
    def label(self) -> str:
        return KINDS[self.kind][1]


def past_years(text: str, current_year: int) -> List[int]:
    return [int(y) for y in YEAR.findall(text) if 2000 <= int(y) < current_year]


def _version_hits(sentence: str) -> List[str]:
    hits = [m.group(0) for m in VERSION_EXPLICIT.finditer(sentence)]
    hits += [m.group(0) for m in VERSION_NAMED.finditer(sentence)]
    for match in VERSION_DOTTED.finditer(sentence):
        if match.group(1) not in NOT_PRODUCTS:
            hits.append(match.group(0))
    unique = []
    for hit in hits:
        if not any(hit in other or other in hit for other in unique):
            unique.append(hit)
    return unique


def sentence_findings(sentence: str, current_year: int) -> List[Finding]:
    """Every signal found in one sentence. A sentence counts once per kind."""
    findings: List[Finding] = []
    years = past_years(sentence, current_year)
    if years:
        year_text = ", ".join(str(y) for y in sorted(set(years)))
        if FUTURE_CUES.search(sentence):
            findings.append(Finding("future_in_past", sentence, year_text))
        elif HISTORY_CUES.search(sentence):
            pass  # "founded in 2015" is history, not a fact that drifts.
        elif CURRENT_CUES.search(sentence):
            findings.append(Finding("past_year_as_current", sentence, year_text))
        else:
            findings.append(Finding("dated", sentence, year_text))
    versions = _version_hits(sentence)
    if versions:
        findings.append(Finding("version", sentence, ", ".join(versions[:3])))
    prices = PRICE.findall(sentence)
    if prices or PLAN.search(sentence):
        findings.append(Finding("price", sentence, ", ".join(p.strip() for p in prices[:3])))
    relative = TIME_RELATIVE.search(sentence)
    if relative and not years:
        findings.append(Finding("time_relative", sentence, relative.group(0)))
    return findings


@dataclass
class PageScore:
    url: str
    title: str
    last_changed: str
    date_source: str
    age_months: Optional[int]
    findings: List[Finding]
    word_count: int
    error: str = ""

    @property
    def score(self) -> int:
        return sum(f.weight for f in self.findings)

    def count(self, kind: str) -> int:
        return sum(1 for f in self.findings if f.kind == kind)


def months_between(start: str, today: date) -> Optional[int]:
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", start or "")
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    return max(0, (today.year - year) * 12 + today.month - month)


def score_page(page, sitemap_lastmod: str = "", today: Optional[date] = None) -> PageScore:
    from .extract import best_date

    today = today or date.today()
    findings: List[Finding] = []
    heading = page.h1 or page.title
    title_years = past_years(heading, today.year) or past_years(page.title, today.year)
    if title_years:
        findings.append(Finding("year_in_title", heading, ", ".join(str(y) for y in sorted(set(title_years)))))
    seen = {heading.strip()} if heading else set()
    for sentence in page.sentences:
        if sentence in seen:
            continue
        seen.add(sentence)
        findings.extend(sentence_findings(sentence, today.year))
    last_changed, source = best_date(page, sitemap_lastmod)
    age = months_between(last_changed, today)
    if age is not None and age >= 12:
        # Wording such as "currently" weighs more on a page nobody has touched for a year.
        for finding in findings:
            if finding.kind == "time_relative":
                finding.extra = 1
                finding.detail += " (page unchanged for 12+ months)"
    return PageScore(
        url=page.url,
        title=page.title or page.h1,
        last_changed=last_changed,
        date_source=source,
        age_months=age,
        findings=findings,
        word_count=page.word_count,
    )
