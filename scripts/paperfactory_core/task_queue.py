"""Persistent task queue for long-running PaperFactory cycles."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


QUEUE_DIR = "queue"
TASKS_FILE = "queue/tasks.jsonl"
VALID_STATUSES = {"pending", "running", "done", "failed", "blocked", "skipped"}


def iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def stable_id(*parts: Any) -> str:
    raw = "\n".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]


def tasks_path(root: Path) -> Path:
    return root / TASKS_FILE


def read_tasks(root: Path) -> list[dict[str, Any]]:
    path = tasks_path(root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def write_tasks(root: Path, tasks: list[dict[str, Any]]) -> None:
    path = tasks_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(task, ensure_ascii=False, sort_keys=True) + "\n")


def task_status_for_artifact(root: Path, rel: str) -> str:
    path = root / rel
    try:
        if path.exists() and path.stat().st_size > 0:
            return "done"
    except OSError:
        pass
    return "pending"


def artifact_task(root: Path, phase_key: str, rel: str, priority: int) -> dict[str, Any]:
    status = task_status_for_artifact(root, rel)
    return {
        "id": f"artifact_{stable_id(phase_key, rel)}",
        "phase": phase_key,
        "status": status,
        "priority": priority,
        "kind": "required_artifact",
        "title": f"Produce {rel}",
        "prompt": f"Create or update required artifact `{rel}` for phase `{phase_key}`.",
        "expected_output": rel,
        "dependent_artifacts": [],
        "timeout_minutes": 120,
        "retry_count": 0,
        "updated_at": iso_now(),
    }


def self_check_task(phase_key: str, report_status: str | None, review_gate: str = "phase_self_review") -> dict[str, Any]:
    done = str(report_status or "").lower() in {"complete", "completed", "pass", "passed"}
    return {
        "id": f"self_check_{stable_id(phase_key)}",
        "phase": phase_key,
        "status": "done" if done else "pending",
        "priority": 90,
        "kind": "self_check",
        "title": f"Run {review_gate}",
        "prompt": (
            "Run the execute -> self-check -> repair -> evidence-check -> report -> route loop. "
            f"Record the result in reports/{phase_key}.json."
        ),
        "expected_output": f"reports/{phase_key}.json",
        "dependent_artifacts": [],
        "timeout_minutes": 60,
        "retry_count": 0,
        "updated_at": iso_now(),
    }


def preserve_runtime_fields(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    if old.get("status") in {"running", "failed", "blocked"} and new.get("status") != "done":
        new["status"] = old["status"]
    for key in ("retry_count", "started_at", "completed_at", "last_error", "notes"):
        if key in old and key not in new:
            new[key] = old[key]
    return new


def refresh_phase_tasks(
    root: Path,
    phase: Any | None,
    *,
    missing: list[str],
    report_status: str | None,
    review_gate: str = "phase_self_review",
) -> dict[str, Any]:
    existing = read_tasks(root)
    by_id = {str(item.get("id")): item for item in existing if isinstance(item, dict) and item.get("id")}
    generated: list[dict[str, Any]] = []
    if phase is not None:
        phase_key = str(getattr(phase, "key", ""))
        required = list(getattr(phase, "required", ()))
        for index, rel in enumerate(required):
            generated.append(artifact_task(root, phase_key, str(rel), priority=20 + index))
        generated.append(self_check_task(phase_key, report_status, review_gate=review_gate))

    merged = dict(by_id)
    for task in generated:
        old = by_id.get(task["id"], {})
        merged[task["id"]] = preserve_runtime_fields(old, task)
    tasks = sorted(merged.values(), key=lambda item: (int(item.get("priority", 100)), str(item.get("id", ""))))
    write_tasks(root, tasks)
    return summarize(tasks, active_phase=None if phase is None else str(getattr(phase, "key", "")), missing=missing)


def summarize(tasks: list[dict[str, Any]], *, active_phase: str | None = None, missing: list[str] | None = None) -> dict[str, Any]:
    counts = {status: 0 for status in VALID_STATUSES}
    for task in tasks:
        status = str(task.get("status") or "pending")
        counts[status if status in counts else "pending"] += 1
    pending = [
        task
        for task in tasks
        if str(task.get("status") or "pending") == "pending"
        and (active_phase is None or task.get("phase") == active_phase)
    ]
    pending.sort(key=lambda item: (int(item.get("priority", 100)), str(item.get("id", ""))))
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "active_phase": active_phase,
        "counts": counts,
        "missing_artifacts": missing or [],
        "next_task": pending[0] if pending else None,
        "tasks_file": TASKS_FILE,
    }

