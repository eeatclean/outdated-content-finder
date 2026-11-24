"""Write the ranked list to the terminal, CSV, JSON or Markdown."""

from __future__ import annotations

import csv
import json
from typing import IO, List

from .signals import KINDS, PageScore

COLUMNS = ["year_in_title", "past_year_as_current", "future_in_past", "version", "price", "time_relative", "dated"]
SHORT = {
    "year_in_title": "title",
    "past_year_as_current": "stale",
    "future_in_past": "future",
    "version": "ver",
    "price": "price",
    "time_relative": "rel",
    "dated": "year",
}


def rank(scores: List[PageScore]) -> List[PageScore]:
    ok = [s for s in scores if not s.error]
    return sorted(ok, key=lambda s: (-s.score, -(s.age_months or 0), s.url))


def _age(score: PageScore) -> str:
    if score.age_months is None:
        return "?"
    if score.age_months >= 24:
        return f"{score.age_months // 12}y"
    return f"{score.age_months}m"


def print_table(scores: List[PageScore], out: IO, top: int = 20) -> None:
    ranked = rank(scores)[:top]
    if not ranked:
        out.write("No page could be analyzed.\n")
        return
    header = f"{'#':>3} {'score':>5} {'age':>4}  " + " ".join(f"{SHORT[c]:>6}" for c in COLUMNS) + "  url\n"
    out.write(header)
    for i, s in enumerate(ranked, 1):
        counts = " ".join(f"{s.count(c):>6}" for c in COLUMNS)
        out.write(f"{i:>3} {s.score:>5} {_age(s):>4}  {counts}  {s.url}\n")
    out.write(
        "\nColumns: title = past year in the title, stale = past year presented as current, "
        "future = future event dated in a past year,\nver = version or model number, price = price or plan, "
        "rel = time-relative wording, year = other dated reference. age = since the last known change.\n"
    )


def write_csv(scores: List[PageScore], out: IO) -> None:
    writer = csv.writer(out)
    writer.writerow(["rank", "url", "title", "score", "last_changed", "date_source", "age_months", "words"]
                    + COLUMNS + ["first_sentence_to_check", "error"])
    ranked = rank(scores)
    failed = [s for s in scores if s.error]
    for i, s in enumerate(ranked + failed, 1):
        strongest = max(s.findings, key=lambda f: f.weight, default=None)
        writer.writerow(
            [i if not s.error else "", s.url, s.title, s.score if not s.error else "", s.last_changed,
             s.date_source, "" if s.age_months is None else s.age_months, s.word_count]
            + [s.count(c) for c in COLUMNS]
            + [strongest.sentence[:300] if strongest else "", s.error]
        )


def to_dict(s: PageScore) -> dict:
    return {
        "url": s.url,
        "title": s.title,
        "score": s.score,
        "last_changed": s.last_changed,
        "date_source": s.date_source,
        "age_months": s.age_months,
        "words": s.word_count,
        "error": s.error,
        "counts": {c: s.count(c) for c in COLUMNS},
        "findings": [
            {"kind": f.kind, "label": f.label, "weight": f.weight, "detail": f.detail, "sentence": f.sentence}
            for f in s.findings
        ],
    }


def write_json(scores: List[PageScore], out: IO) -> None:
    data = [to_dict(s) for s in rank(scores)] + [to_dict(s) for s in scores if s.error]
    json.dump(data, out, ensure_ascii=False, indent=2)
    out.write("\n")


def write_markdown(scores: List[PageScore], out: IO, top: int = 20, per_page: int = 8) -> None:
    ranked = rank(scores)[:top]
    out.write("# Pages to check first\n\n")
    out.write(
        "Each sentence below is a candidate, not a verdict. Check it against the official source "
        "(release notes, pricing page, standard, regulator) before you change anything.\n\n"
    )
    for i, s in enumerate(ranked, 1):
        out.write(f"## {i}. {s.title or s.url}\n\n")
        out.write(f"- URL: {s.url}\n- Score: {s.score}\n")
        out.write(f"- Last known change: {s.last_changed or 'unknown'}"
                  f"{' (' + s.date_source + ')' if s.date_source else ''}\n\n")
        order = sorted(s.findings, key=lambda f: -f.weight)
        shown = set()
        count = 0
        for f in order:
            if f.sentence in shown:
                continue
            shown.add(f.sentence)
            kinds = sorted({g.label for g in s.findings if g.sentence == f.sentence})
            sentence = f.sentence if len(f.sentence) <= 280 else f.sentence[:277] + "..."
            out.write(f"- **{' · '.join(kinds)}**: {sentence}\n")
            count += 1
            if count >= per_page:
                break
        if not s.findings:
            out.write("- Nothing time-sensitive spotted.\n")
        out.write("\n")
    failed = [s for s in scores if s.error]
    if failed:
        out.write("## Pages that could not be read\n\n")
        for s in failed:
            out.write(f"- {s.url}: {s.error}\n")


__all__ = ["print_table", "write_csv", "write_json", "write_markdown", "rank", "KINDS"]
