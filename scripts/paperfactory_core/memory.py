"""Generated cross-phase memory bundle for PaperFactory research runs."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any


MEMORY_DIR = "memory"
WORKFLOW_CONFIG = "workflow.json"
MEMORY_ARTIFACT_LIMIT = 500
MEMORY_RECENT_PHASE_LIMIT = 12
COMPLETE_STATUSES = {"complete", "completed", "pass", "passed"}
ROUTE_DECISIONS = {
    "advance",
    "repeat",
    "redo",
    "jump_back",
    "jump_to",
    "skip_next",
    "skip_to",
}
MEMORY_SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "archive",
    "logs",
    "memory",
    "progress",
}
MEMORY_TEXT_EXTENSIONS = {
    ".bib",
    ".csv",
    ".json",
    ".md",
    ".tex",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}


def iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def memory_path(root: Path, filename: str) -> Path:
    return root / MEMORY_DIR / filename


def compact_text(value: Any, limit: int = 1200) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def normalize_list(value: Any, *, limit: int = 30, text_limit: int = 500) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    else:
        items = [value]
    normalized: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        else:
            text = str(item)
        text = compact_text(text, text_limit)
        if text:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def normalize_route_decision(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = {"decision": raw}
    if not isinstance(raw, dict):
        return None
    decision = str(raw.get("decision") or raw.get("action") or "advance").strip().lower()
    if decision not in ROUTE_DECISIONS:
        return None
    return {
        "decision": "repeat" if decision == "redo" else decision,
        "target_phase": str(raw.get("target_phase") or raw.get("target") or "").strip(),
        "reason": compact_text(raw.get("reason") or "", 700),
        "confidence": raw.get("confidence"),
    }


def artifact_role(rel: Path) -> str:
    parts = rel.parts
    if not parts:
        return "artifact"
    top = parts[0]
    if rel.as_posix() in {"state.json", "task.md", WORKFLOW_CONFIG}:
        return "control"
    if top == "reports":
        return "phase_report"
    if top == "pages":
        return "phase_page"
    if top == "paper":
        return "paper"
    if top == "figures":
        return "figure"
    if top == "experiments":
        return "experiment"
    if top in {"scope", "literature", "baselines", "data", "method", "results", "reviews", "custom"}:
        return top
    return "artifact"


def phase_hint_for_artifact(rel: Path) -> str:
    parts = rel.parts
    if not parts:
        return ""
    top = parts[0]
    if top == "reports" and rel.suffix == ".json":
        return rel.stem
    if top == "pages" and rel.suffix == ".md":
        return rel.stem
    if top == "custom":
        return rel.stem
    if top == "scope":
        return "scope"
    if top == "literature":
        return "survey"
    if top == "data":
        return "data_sanity"
    if top == "method":
        return "method_design"
    if top == "results":
        return "paper_evidence"
    if top == "reviews":
        return "internal_review"
    if top == "paper":
        return "paper_drafting"
    if top == "figures":
        return "paper_evidence"
    if top == "experiments" and len(parts) > 1:
        if parts[1].startswith("cheap"):
            return "cheap_baselines"
        if parts[1].startswith("method"):
            return "method_smoke"
        if parts[1].startswith("advanced"):
            return "advanced_comparison"
    if top == "baselines" and len(parts) > 1 and "advanced" in parts[1]:
        return "advanced_comparison"
    if top == "baselines":
        return "cheap_baselines"
    return ""


def iter_memory_artifact_files(root: Path):
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        try:
            rel_dir = current.relative_to(root)
        except ValueError:
            continue
        if rel_dir.parts and rel_dir.parts[0] in MEMORY_SKIP_DIRS:
            dirnames[:] = []
            continue
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in MEMORY_SKIP_DIRS and not dirname.startswith(".")
        ]
        for filename in filenames:
            if filename.endswith((".tmp", ".lock", ".pyc", ".pyo")):
                continue
            path = current / filename
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if rel.parts and rel.parts[0] in MEMORY_SKIP_DIRS:
                continue
            yield path, rel


def build_artifact_index(root: Path, phase: Any | None) -> dict[str, Any]:
    required = set(getattr(phase, "required", ()) if phase else ())
    rows: list[dict[str, Any]] = []
    for path, rel in iter_memory_artifact_files(root) or []:
        try:
            stat = path.stat()
        except OSError:
            continue
        suffix = path.suffix.lower()
        rel_text = rel.as_posix()
        rows.append(
            {
                "path": rel_text,
                "role": artifact_role(rel),
                "phase_hint": phase_hint_for_artifact(rel),
                "bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                "extension": suffix,
                "text_like": suffix in MEMORY_TEXT_EXTENSIONS,
                "required_current_phase": rel_text in required,
            }
        )

    priority = {
        "control": 0,
        "phase_report": 1,
        "scope": 2,
        "literature": 3,
        "data": 4,
        "baselines": 5,
        "method": 6,
        "experiment": 7,
        "figure": 8,
        "results": 9,
        "paper": 10,
        "reviews": 11,
        "custom": 12,
        "phase_page": 13,
        "artifact": 20,
    }
    rows.sort(
        key=lambda row: (
            0 if row["required_current_phase"] else 1,
            priority.get(str(row["role"]), 20),
            str(row["path"]),
        )
    )
    limited = rows[:MEMORY_ARTIFACT_LIMIT]
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "current_phase": "complete" if phase is None else getattr(phase, "key", ""),
        "total_indexed": len(rows),
        "truncated": len(rows) > len(limited),
        "artifacts": limited,
    }


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def collect_phase_report_records(root: Path) -> list[dict[str, Any]]:
    reports_dir = root / "reports"
    if not reports_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(reports_dir.glob("*.json")):
        report = read_json(path)
        if not isinstance(report, dict):
            continue
        phase_key = str(report.get("phase") or path.stem)
        route = normalize_route_decision(
            report.get("route") or report.get("routing") or report.get("phase_route")
        )
        records.append(
            {
                "phase": phase_key,
                "report": f"reports/{path.name}",
                "status": str(report.get("status") or "unknown"),
                "summary": compact_text(report.get("summary") or report.get("result") or "", 1200),
                "evidence": normalize_list(report.get("evidence"), limit=40, text_limit=500),
                "risks": normalize_list(report.get("risks") or report.get("risk"), limit=40, text_limit=500),
                "next": compact_text(report.get("next") or report.get("next_action") or "", 900),
                "cleanup": report.get("cleanup") if isinstance(report.get("cleanup"), dict) else {},
                "route": route,
            }
        )
    return records


def write_phase_summaries(root: Path, records: list[dict[str, Any]]) -> None:
    path = memory_path(root, "phase_summaries.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_text_excerpt(path: Path, limit: int = 1800) -> str:
    if path.suffix.lower() not in MEMORY_TEXT_EXTENSIONS:
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return text.strip()[:limit]


def build_decision_memory(state: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    report_routes = []
    for record in records:
        route = record.get("route")
        if isinstance(route, dict):
            report_routes.append(
                {
                    "phase": record.get("phase"),
                    "report": record.get("report"),
                    **route,
                }
            )
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "current_phase": state.get("phase"),
        "phase_history": state.get("phase_history", [])[-50:],
        "controller_routes": state.get("phase_routes", [])[-50:],
        "report_routes": report_routes[-50:],
    }


def build_risk_memory(state: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    risks: list[dict[str, Any]] = []
    for record in records:
        for risk in record.get("risks", []):
            risks.append({"phase": record.get("phase"), "report": record.get("report"), "risk": risk})
        status = str(record.get("status") or "").lower()
        if status and status not in COMPLETE_STATUSES:
            risks.append(
                {
                    "phase": record.get("phase"),
                    "report": record.get("report"),
                    "risk": f"Report status is {status}; phase may need attention.",
                }
            )
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "current_phase": state.get("phase"),
        "open_risks": risks[-80:],
    }


def build_claim_memory(root: Path) -> dict[str, Any]:
    source_rels = (
        "paper/claim_evidence_map.md",
        "results/main_results.md",
        "results/ablations.md",
        "results/failure_cases.md",
        "results/experiment_analysis.md",
        "literature/novelty_gap.md",
        "method/atomic_concepts.md",
        "method/method_design.md",
    )
    sources: list[dict[str, str]] = []
    for rel in source_rels:
        path = root / rel
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size == 0:
            continue
        excerpt = read_text_excerpt(path)
        sources.append({"path": rel, "excerpt": excerpt})
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "sources": sources,
        "rule": "Only claims backed by explicit artifact evidence may be used as factual paper claims.",
    }


def build_handoff_markdown(
    root: Path,
    state: dict[str, Any],
    phase: Any | None,
    *,
    phase_status: str,
    missing: list[str],
    records: list[dict[str, Any]],
    artifact_index: dict[str, Any],
    decision_memory: dict[str, Any],
    risk_memory: dict[str, Any],
    claim_memory: dict[str, Any],
) -> str:
    phase_key = "complete" if phase is None else getattr(phase, "key", "")
    phase_title = "Complete" if phase is None else getattr(phase, "title", "")
    lines = [
        "# Research Memory Handoff",
        "",
        f"- Updated: {iso_now()}",
        f"- Task: {state.get('task', '')}",
        f"- Current phase: `{phase_key}` - {phase_title}",
        f"- Current report status: {phase_status}",
        "",
        "## Read Order",
        "",
        "1. `.research/memory/handoff.md`",
        "2. `.research/state.json` and `.research/task.md`",
        "3. `.research/memory/phase_summaries.jsonl`",
        "4. `.research/memory/decision_memory.json` and `.research/memory/risk_memory.json`",
        "5. `.research/memory/artifact_index.json`",
        "6. Current phase required artifacts and any human intervention notes",
        "",
        "## Active Gate",
        "",
    ]
    if phase is None:
        lines.append("The workflow is complete. Review final artifacts and residual risks only.")
    else:
        lines.extend(
            [
                str(getattr(phase, "gate", "")),
                "",
                "Required artifacts:",
            ]
        )
        missing_set = set(missing)
        for rel in getattr(phase, "required", ()):
            marker = "missing" if rel in missing_set else "present"
            lines.append(f"- `{rel}`: {marker}")
    lines.extend(["", "## Recent Phase Outcomes", ""])
    if records:
        for record in records[-MEMORY_RECENT_PHASE_LIMIT:]:
            summary = record.get("summary") or record.get("next") or "No summary recorded."
            lines.append(
                f"- `{record.get('phase')}` status `{record.get('status')}`: {compact_text(summary, 350)}"
            )
    else:
        lines.append("- No phase reports have been written yet.")

    lines.extend(["", "## Route And Decision Memory", ""])
    routes = list(decision_memory.get("controller_routes") or [])[-8:]
    report_routes = list(decision_memory.get("report_routes") or [])[-8:]
    if routes or report_routes:
        for route in routes:
            lines.append(
                f"- Controller route `{route.get('from_phase')}` -> `{route.get('resolved_next_phase')}`: "
                f"{route.get('decision')} ({compact_text(route.get('reason'), 220)})"
            )
        for route in report_routes:
            lines.append(
                f"- Report route `{route.get('phase')}`: {route.get('decision')} -> "
                f"{route.get('target_phase') or route.get('resolved_next_phase') or 'default'} "
                f"({compact_text(route.get('reason'), 220)})"
            )
    else:
        lines.append("- No route decisions recorded yet.")

    lines.extend(["", "## Open Risks", ""])
    open_risks = list(risk_memory.get("open_risks") or [])[-15:]
    if open_risks:
        for item in open_risks:
            lines.append(f"- `{item.get('phase')}`: {compact_text(item.get('risk'), 280)}")
    else:
        lines.append("- No open risks recorded in phase reports.")

    lines.extend(["", "## High-Value Artifacts", ""])
    artifact_rows = list(artifact_index.get("artifacts") or [])
    required_rows = [row for row in artifact_rows if row.get("required_current_phase")]
    other_rows = [row for row in artifact_rows if not row.get("required_current_phase")]
    selected = (required_rows + other_rows)[:25]
    if selected:
        for row in selected:
            required_label = " required" if row.get("required_current_phase") else ""
            lines.append(
                f"- `{row.get('path')}` ({row.get('role')}, {row.get('bytes')} bytes{required_label})"
            )
    else:
        lines.append("- No artifacts indexed yet.")

    lines.extend(["", "## Claim And Evidence Notes", ""])
    claim_sources = list(claim_memory.get("sources") or [])
    if claim_sources:
        for source in claim_sources:
            lines.append(f"- Review `{source.get('path')}` before making or revising paper claims.")
    else:
        lines.append("- No claim/evidence source files exist yet.")

    lines.extend(
        [
            "",
            "## Memory Contract",
            "",
            "- Treat this handoff as the cross-phase memory entry point; do not rely on chat history.",
            "- If new evidence changes direction, update the relevant artifact and phase report rather than only writing a log.",
            "- Keep `results/summary.md` concise and cumulative; detailed evidence belongs in phase artifacts.",
        ]
    )
    return "\n".join(lines) + "\n"


def refresh_memory(
    root: Path,
    state: dict[str, Any],
    phase: Any | None,
    *,
    phase_status: str,
    missing: list[str],
) -> dict[str, Any]:
    (root / MEMORY_DIR).mkdir(parents=True, exist_ok=True)
    records = collect_phase_report_records(root)
    artifact_index = build_artifact_index(root, phase)
    decision_memory = build_decision_memory(state, records)
    risk_memory = build_risk_memory(state, records)
    claim_memory = build_claim_memory(root)

    write_json(memory_path(root, "artifact_index.json"), artifact_index)
    write_phase_summaries(root, records)
    write_json(memory_path(root, "decision_memory.json"), decision_memory)
    write_json(memory_path(root, "risk_memory.json"), risk_memory)
    write_json(memory_path(root, "claim_memory.json"), claim_memory)
    memory_path(root, "handoff.md").write_text(
        build_handoff_markdown(
            root,
            state,
            phase,
            phase_status=phase_status,
            missing=missing,
            records=records,
            artifact_index=artifact_index,
            decision_memory=decision_memory,
            risk_memory=risk_memory,
            claim_memory=claim_memory,
        ),
        encoding="utf-8",
    )
    return {
        "memory_dir": str(root / MEMORY_DIR),
        "current_phase": "complete" if phase is None else getattr(phase, "key", ""),
        "reports": len(records),
        "artifacts": int(artifact_index.get("total_indexed") or 0),
        "claim_sources": len(claim_memory.get("sources") or []),
    }

