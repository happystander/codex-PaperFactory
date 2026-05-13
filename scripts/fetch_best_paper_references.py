#!/usr/bin/env python3
"""Download curated best-paper PDFs and arXiv source bundles into a local cache."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "reference_papers" / "manifest.json"
DEFAULT_OUTPUT = ROOT / "reference_papers" / "cache"
USER_AGENT = "Codex-PaperFactory/0.1 (+https://github.com/happystander/codex-PaperFactory)"


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def download(url: str, target: Path, timeout: int, overwrite: bool) -> tuple[str, str]:
    if target.exists() and target.stat().st_size > 0 and not overwrite:
        return "cached", str(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        return "error", str(exc)
    target.write_bytes(data)
    return "downloaded", str(target)


def selected_papers(papers: list[dict[str, Any]], ids: set[str], venues: set[str], limit: int | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for paper in papers:
        if ids and str(paper.get("id")) not in ids:
            continue
        venue_values = {str(paper.get("venue", "")).lower(), str(paper.get("venue_alias", "")).lower()}
        if venues and not (venue_values & venues):
            continue
        rows.append(paper)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Best-paper manifest JSON")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Local cache directory")
    parser.add_argument("--id", action="append", default=[], help="Paper id to fetch; may repeat")
    parser.add_argument("--venue", action="append", default=[], help="Venue filter such as ICLR, NeurIPS, ICML, ACL, AAAI")
    parser.add_argument("--limit", type=int, help="Maximum papers to fetch after filters")
    parser.add_argument("--pdf-only", action="store_true", help="Fetch PDFs only")
    parser.add_argument("--source-only", action="store_true", help="Fetch source bundles only")
    parser.add_argument("--metadata-only", action="store_true", help="Write metadata files but do not download")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing cached files")
    parser.add_argument("--timeout", type=int, default=60, help="Download timeout in seconds")
    parser.add_argument("--sleep", type=float, default=1.0, help="Delay between downloads")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    manifest = load_manifest(manifest_path)
    papers = selected_papers(
        list(manifest.get("papers", [])),
        set(args.id),
        {item.lower() for item in args.venue},
        args.limit,
    )
    if args.pdf_only and args.source_only:
        raise SystemExit("--pdf-only and --source-only cannot be used together")

    output_dir.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []
    for paper in papers:
        paper_id = str(paper["id"])
        paper_dir = output_dir / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / "metadata.json").write_text(json.dumps(paper, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        row: dict[str, Any] = {"id": paper_id, "title": paper.get("title"), "files": {}}
        if not args.metadata_only:
            if not args.source_only and paper.get("pdf_url"):
                status, detail = download(str(paper["pdf_url"]), paper_dir / "paper.pdf", args.timeout, args.overwrite)
                row["files"]["pdf"] = {"status": status, "detail": detail}
                time.sleep(args.sleep)
            if not args.pdf_only and paper.get("source_url"):
                status, detail = download(str(paper["source_url"]), paper_dir / "source.tar", args.timeout, args.overwrite)
                row["files"]["source"] = {"status": status, "detail": detail}
                time.sleep(args.sleep)
        summary.append(row)

    summary_path = output_dir / "fetch_summary.json"
    summary_path.write_text(json.dumps({"manifest": str(manifest_path), "papers": summary}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Fetched metadata for {len(summary)} paper(s).")
    print(f"Cache: {output_dir}")
    print(f"Summary: {summary_path}")
    for row in summary:
        pieces = []
        for kind, result in row["files"].items():
            pieces.append(f"{kind}={result['status']}")
        suffix = " " + ", ".join(pieces) if pieces else ""
        print(f"- {row['id']}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
