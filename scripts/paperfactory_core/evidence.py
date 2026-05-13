"""Evidence registry for claim-safe long-horizon research."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


EVIDENCE_DIR = "evidence"
REGISTRY_FILE = "evidence/registry.json"


def iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "\n".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def registry_path(root: Path) -> Path:
    return root / REGISTRY_FILE


def empty_registry(task: str = "") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "task": task,
        "claims": [],
        "artifacts": [],
        "experiments": [],
        "rejections": [],
        "summary": {
            "claims_total": 0,
            "claims_verified": 0,
            "paper_safe_claims": 0,
            "artifacts_total": 0,
            "open_rejections": 0,
        },
    }


def read_registry(root: Path, task: str = "") -> dict[str, Any]:
    path = registry_path(root)
    if not path.exists():
        return empty_registry(task)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_registry(task)
    if not isinstance(data, dict):
        return empty_registry(task)
    data.setdefault("task", task)
    data.setdefault("claims", [])
    data.setdefault("artifacts", [])
    data.setdefault("experiments", [])
    data.setdefault("rejections", [])
    return data


def write_registry(root: Path, registry: dict[str, Any]) -> None:
    registry["updated_at"] = iso_now()
    registry["summary"] = summarize_registry(registry)
    path = registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def artifact_kind(rel: str) -> str:
    if rel.endswith("metrics.json") or "/metrics" in rel:
        return "metric_source"
    if rel.startswith("figures/"):
        return "figure_or_table_source"
    if rel.startswith("experiments/"):
        return "experiment_artifact"
    if rel.startswith("paper/"):
        return "paper_artifact"
    if rel.startswith("results/"):
        return "result_summary"
    if rel.startswith("literature/"):
        return "literature_support"
    return "artifact"


def artifact_entry(root: Path, rel: str, phase: str, source: str) -> dict[str, Any]:
    path = root / rel
    exists = path.exists()
    stat = None
    if exists:
        try:
            stat = path.stat()
        except OSError:
            stat = None
    return {
        "id": stable_id("artifact", rel),
        "path": rel,
        "phase": phase,
        "kind": artifact_kind(rel),
        "exists": exists,
        "bytes": stat.st_size if stat else 0,
        "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat() if stat else "",
        "source": source,
    }


def report_paths(root: Path) -> list[Path]:
    reports = root / "reports"
    if not reports.exists():
        return []
    return sorted(path for path in reports.glob("*.json") if path.is_file())


def read_report(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def normalize_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def command_or_metric_sources(report: dict[str, Any]) -> tuple[list[str], list[str]]:
    commands = normalize_items(report.get("commands") or report.get("command"))
    metrics = normalize_items(report.get("metrics") or report.get("metric_source") or report.get("metric_sources"))
    return commands, metrics


def report_to_registry_rows(root: Path, path: Path, report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    phase = str(report.get("phase") or path.stem)
    status = str(report.get("status") or "unknown").lower()
    source = f"report:{path.name}"
    evidence_paths = normalize_items(report.get("evidence"))
    commands, metrics = command_or_metric_sources(report)
    artifacts = [artifact_entry(root, rel, phase, source) for rel in evidence_paths]
    artifacts.extend(artifact_entry(root, rel, phase, source) for rel in metrics if "/" in rel or rel.endswith(".json"))

    claim_texts = normalize_items(report.get("claims") or report.get("claim"))
    summary = str(report.get("summary") or report.get("result") or "").strip()
    if summary and not claim_texts:
        claim_texts = [summary]
    artifact_ids = [item["id"] for item in artifacts if item.get("exists")]
    confidence = None
    route = report.get("route") if isinstance(report.get("route"), dict) else {}
    if isinstance(route, dict) and isinstance(route.get("confidence"), (int, float)):
        confidence = float(route["confidence"])
    verified = status == "complete" and bool(artifact_ids)
    claims = [
        {
            "id": stable_id("claim", phase, text),
            "phase": phase,
            "claim": text,
            "status": "verified" if verified else "candidate",
            "supporting_artifacts": artifact_ids,
            "experiment_commands": commands,
            "metric_sources": metrics,
            "figure_table_sources": [item["path"] for item in artifacts if item["kind"] == "figure_or_table_source"],
            "confidence": confidence,
            "paper_safe": bool(verified and confidence is not None and confidence >= 0.6),
            "source": source,
            "updated_at": iso_now(),
        }
        for text in claim_texts
    ]
    experiments = [
        {
            "id": stable_id("experiment", phase, command),
            "phase": phase,
            "command": command,
            "metric_sources": metrics,
            "supporting_artifacts": artifact_ids,
            "source": source,
        }
        for command in commands
    ]
    rejections = []
    if status in {"blocked", "failed", "needs_more_work", "error"} or report.get("risks"):
        for risk in normalize_items(report.get("risks") or report.get("risk") or status):
            rejections.append(
                {
                    "id": stable_id("rejection", phase, risk),
                    "phase": phase,
                    "reason": risk,
                    "status": "open",
                    "source": source,
                }
            )
    return claims, artifacts, experiments, rejections


def summarize_registry(registry: dict[str, Any]) -> dict[str, int]:
    claims = registry.get("claims") if isinstance(registry.get("claims"), list) else []
    artifacts = registry.get("artifacts") if isinstance(registry.get("artifacts"), list) else []
    rejections = registry.get("rejections") if isinstance(registry.get("rejections"), list) else []
    return {
        "claims_total": len(claims),
        "claims_verified": sum(1 for item in claims if item.get("status") == "verified"),
        "paper_safe_claims": sum(1 for item in claims if item.get("paper_safe")),
        "artifacts_total": len(artifacts),
        "open_rejections": sum(1 for item in rejections if item.get("status") == "open"),
    }


def merge_by_id(existing: list[dict[str, Any]], generated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in existing:
        if isinstance(item, dict) and item.get("id"):
            rows[str(item["id"])] = item
    for item in generated:
        rows[str(item["id"])] = item
    return list(rows.values())


def sync_registry(root: Path, task: str = "") -> dict[str, Any]:
    registry = read_registry(root, task)
    generated_claims: list[dict[str, Any]] = []
    generated_artifacts: list[dict[str, Any]] = []
    generated_experiments: list[dict[str, Any]] = []
    generated_rejections: list[dict[str, Any]] = []
    for path in report_paths(root):
        report = read_report(path)
        if not report:
            continue
        claims, artifacts, experiments, rejections = report_to_registry_rows(root, path, report)
        generated_claims.extend(claims)
        generated_artifacts.extend(artifacts)
        generated_experiments.extend(experiments)
        generated_rejections.extend(rejections)

    registry["schema_version"] = 1
    registry["task"] = registry.get("task") or task
    registry["claims"] = merge_by_id(registry.get("claims", []), generated_claims)
    registry["artifacts"] = merge_by_id(registry.get("artifacts", []), generated_artifacts)
    registry["experiments"] = merge_by_id(registry.get("experiments", []), generated_experiments)
    registry["rejections"] = merge_by_id(registry.get("rejections", []), generated_rejections)
    write_registry(root, registry)
    return registry

