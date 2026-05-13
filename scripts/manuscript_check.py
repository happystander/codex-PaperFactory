#!/usr/bin/env python3
"""Lightweight manuscript hygiene checks for PaperFactory."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


AI_TONE = [
    "delve",
    "tapestry",
    "underscore",
    "realm",
    "landscape",
    "pivotal",
    "robust",
    "seamless",
    "comprehensive",
]

OVERCLAIM = [
    "state-of-the-art",
    "sota",
    "solves",
    "prove",
    "guarantee",
    "universal",
    "always",
    "never fails",
]


def line_findings(text: str, terms: list[str], kind: str) -> list[dict]:
    findings = []
    for line_no, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for term in terms:
            if term in low:
                findings.append({"kind": kind, "line": line_no, "term": term, "text": line.strip()[:180]})
    return findings


def regex_line_findings(text: str, patterns: list[tuple[str, str]], kind: str) -> list[dict]:
    findings = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for term, pattern in patterns:
            if re.search(pattern, line):
                findings.append({"kind": kind, "line": line_no, "term": term, "text": line.strip()[:180]})
    return findings


def check_structure(text: str) -> list[dict]:
    headings = [line.strip("# ").strip().lower() for line in text.splitlines() if line.lstrip().startswith("#")]
    findings = []
    needed = ["abstract", "introduction", "method", "experiment", "result", "limitation"]
    for item in needed:
        if not any(item in heading for heading in headings):
            findings.append({"kind": "structure", "line": None, "term": item, "text": f"Missing or unclear section: {item}"})
    return findings


def check_latex_refs(text: str) -> list[dict]:
    findings = []
    labels = set(re.findall(r"\\label\{([^}]+)\}", text))
    refs = set(re.findall(r"\\(?:ref|autoref|cref)\{([^}]+)\}", text))
    for ref in sorted(refs - labels):
        findings.append({"kind": "latex-ref", "line": None, "term": ref, "text": "Reference without matching label"})
    return findings


def check_submission_hygiene(text: str, fmt: str) -> list[dict]:
    findings: list[dict] = []
    findings.extend(
        regex_line_findings(
            text,
            [
                ("smart quote", r"[“”‘’]"),
                ("malformed i.e./e.g.", r"\b(?:i\s+e|ie|eg)\s*\.|i\.e(?!\.,)|e\.g(?!\.,)"),
                ("missing prose space before parenthesis", r"(?<!\\)\b[A-Za-z][A-Za-z0-9]*\([^)]{2,}"),
            ],
            "format-hygiene",
        )
    )
    if fmt == "latex":
        findings.extend(
            regex_line_findings(
                text,
                [
                    ("breaking figure/table reference", r"\b(?:Figure|Fig\.|Table|Section|Sec\.|Equation|Eq\.)\s+\\(?:ref|autoref|cref)\{"),
                    ("raw resizebox", r"\\resizebox\{"),
                    ("loose itemize", r"\\begin\{itemize\}(?!\[)"),
                    ("heading ends with period", r"\\(?:section|subsection|subsubsection)\*?\{[^}]*\.\}"),
                    ("arXiv preprint bibliography", r"arXiv preprint|journal\s*=\s*\{arXiv"),
                    ("noisy booktitle date/location", r"booktitle\s*=\s*\{[^}]*\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Vienna|Seattle|Vancouver|Honolulu|Singapore)\b"),
                ],
                "latex-format",
            )
        )
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper")
    parser.add_argument("--format", choices=["markdown", "latex", "typst", "auto"], default="auto")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.paper)
    text = path.read_text(encoding="utf-8", errors="ignore")
    fmt = args.format
    if fmt == "auto":
        fmt = {".tex": "latex", ".typ": "typst"}.get(path.suffix.lower(), "markdown")
    findings = []
    findings.extend(line_findings(text, AI_TONE, "ai-tone"))
    findings.extend(line_findings(text, OVERCLAIM, "overclaim"))
    findings.extend(check_structure(text))
    findings.extend(check_submission_hygiene(text, fmt))
    if fmt == "latex":
        findings.extend(check_latex_refs(text))
    result = {"paper": str(path), "format": fmt, "finding_count": len(findings), "findings": findings}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Paper: {path}")
        print(f"Format: {fmt}")
        print(f"Findings: {len(findings)}")
        for finding in findings[:80]:
            loc = f"line {finding['line']}" if finding["line"] else "global"
            print(f"- [{finding['kind']}] {loc}: {finding['term']} :: {finding['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
