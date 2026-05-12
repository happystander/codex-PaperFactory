#!/usr/bin/env python3
"""Small dependency-free BibTeX search helper for PaperFactory."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,]+)\s*,", re.IGNORECASE)
FIELD_RE = re.compile(r"(\w+)\s*=\s*(?:\{(.*?)\}|\"(.*?)\")\s*,?", re.DOTALL)


def split_entries(text: str) -> list[str]:
    starts = [m.start() for m in re.finditer(r"@\w+\s*\{", text)]
    entries = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
        entries.append(text[start:end].strip())
    return entries


def clean_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    return value.strip("{}\" ")


def parse_entry(raw: str) -> dict[str, Any]:
    first = ENTRY_RE.search(raw)
    key = first.group(1).strip() if first else ""
    fields: dict[str, Any] = {"key": key, "raw": raw}
    for name, braced, quoted in FIELD_RE.findall(raw):
        fields[name.lower()] = clean_value(braced or quoted)
    year = fields.get("year")
    try:
        fields["year_int"] = int(str(year)[:4])
    except Exception:
        fields["year_int"] = None
    return fields


def load_bib(path: Path) -> list[dict[str, Any]]:
    return [parse_entry(raw) for raw in split_entries(path.read_text(encoding="utf-8", errors="ignore"))]


def haystack(entry: dict[str, Any]) -> str:
    fields = ["key", "title", "author", "journal", "booktitle", "keywords", "abstract", "annotation", "note", "doi", "eprint", "url"]
    return " ".join(str(entry.get(field, "")) for field in fields).lower()


def matches(entry: dict[str, Any], args: argparse.Namespace) -> bool:
    text = haystack(entry)
    terms = [term.lower() for term in args.query.split() if term.strip()]
    if terms and not all(term in text for term in terms):
        return False
    if args.author and args.author.lower() not in str(entry.get("author", "")).lower():
        return False
    year = entry.get("year_int")
    if args.year_min is not None and (year is None or year < args.year_min):
        return False
    if args.year_max is not None and (year is None or year > args.year_max):
        return False
    for field in args.has or []:
        if not entry.get(field.lower()):
            return False
    return True


def score(entry: dict[str, Any], query: str) -> int:
    text = haystack(entry)
    return sum(text.count(term.lower()) for term in query.split() if term.strip())


def compact(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": entry.get("key", ""),
        "title": entry.get("title", ""),
        "author": entry.get("author", ""),
        "year": entry.get("year", ""),
        "venue": entry.get("journal") or entry.get("booktitle") or "",
        "doi": entry.get("doi", ""),
        "eprint": entry.get("eprint", ""),
        "url": entry.get("url", ""),
        "latex": {
            "cite": f"\\cite{{{entry.get('key', '')}}}",
            "parencite": f"\\parencite{{{entry.get('key', '')}}}",
            "textcite": f"\\textcite{{{entry.get('key', '')}}}",
        },
        "typst": {
            "cite": f"@{entry.get('key', '')}",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bib", required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--author")
    parser.add_argument("--year-min", type=int)
    parser.add_argument("--year-max", type=int)
    parser.add_argument("--has", action="append")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--format", choices=["json", "markdown", "keys"], default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    entries = load_bib(Path(args.bib))
    hits = [entry for entry in entries if matches(entry, args)]
    hits.sort(key=lambda entry: (score(entry, args.query), entry.get("year_int") or 0), reverse=True)
    hits = hits[: args.limit]
    payload = [compact(entry) for entry in hits]
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.format == "keys":
        print("\n".join(str(entry["key"]) for entry in payload))
    else:
        for entry in payload:
            print(f"- `{entry['key']}` ({entry['year']}): {entry['title']}")
            if entry["venue"]:
                print(f"  - Venue: {entry['venue']}")
            if entry["doi"] or entry["eprint"]:
                print(f"  - DOI/arXiv: {entry['doi'] or entry['eprint']}")
            print(f"  - LaTeX: `{entry['latex']['cite']}`; Typst: `{entry['typst']['cite']}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
