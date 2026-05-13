"""Stop and success conditions for unattended PaperFactory runs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


CONTROL_DIR = "control"
STOP_CONDITIONS_FILE = "control/stop_conditions.json"


def iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def default_stop_conditions() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "max_codex_cycles": None,
        "max_phase_visits": 6,
        "pause_before_phases": [],
        "stop_when_complete": True,
        "success_conditions": {
            "min_paper_safe_claims": 0,
            "require_internal_review_complete": False,
            "require_camera_ready_checklist": False,
        },
        "notes": "Defaults are non-blocking except workflow completion and excessive repeated phase visits.",
    }


def stop_conditions_path(root: Path) -> Path:
    return root / STOP_CONDITIONS_FILE


def read_stop_conditions(root: Path) -> dict[str, Any]:
    path = stop_conditions_path(root)
    if not path.exists():
        return default_stop_conditions()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_stop_conditions()
    if not isinstance(data, dict):
        return default_stop_conditions()
    defaults = default_stop_conditions()
    defaults.update(data)
    defaults["success_conditions"] = {
        **default_stop_conditions()["success_conditions"],
        **(data.get("success_conditions") if isinstance(data.get("success_conditions"), dict) else {}),
    }
    return defaults


def ensure_stop_conditions(root: Path) -> dict[str, Any]:
    config = read_stop_conditions(root)
    path = stop_conditions_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return config


def phase_visit_count(state: dict[str, Any], phase_key: str) -> int:
    count = 1 if state.get("phase") == phase_key else 0
    for item in state.get("phase_history", []):
        if isinstance(item, dict) and item.get("phase") == phase_key:
            count += 1
    return count


def evidence_summary(root: Path) -> dict[str, int]:
    path = root / "evidence" / "registry.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    summary = data.get("summary") if isinstance(data, dict) else {}
    return summary if isinstance(summary, dict) else {}


def success_status(root: Path, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    success = config.get("success_conditions") if isinstance(config.get("success_conditions"), dict) else {}
    evidence = evidence_summary(root)
    checks: list[dict[str, Any]] = []
    min_claims = success.get("min_paper_safe_claims")
    if isinstance(min_claims, int) and min_claims > 0:
        actual = int(evidence.get("paper_safe_claims") or 0)
        checks.append(
            {
                "name": "min_paper_safe_claims",
                "required": min_claims,
                "actual": actual,
                "passed": actual >= min_claims,
            }
        )
    if success.get("require_internal_review_complete"):
        report = root / "reports" / "internal_review.json"
        checks.append({"name": "require_internal_review_complete", "passed": report.exists() and report.stat().st_size > 0})
    if success.get("require_camera_ready_checklist"):
        checklist = root / "paper" / "camera_ready_checklist.md"
        checks.append({"name": "require_camera_ready_checklist", "passed": checklist.exists() and checklist.stat().st_size > 0})
    return {
        "phase": state.get("phase"),
        "checks": checks,
        "passed": all(item.get("passed") for item in checks) if checks else False,
    }


def evaluate_stop(root: Path, state: dict[str, Any], current_phase: str) -> dict[str, Any]:
    config = ensure_stop_conditions(root)
    reasons: list[str] = []
    max_cycles = config.get("max_codex_cycles")
    if isinstance(max_cycles, int) and max_cycles >= 0 and len(state.get("cycles", [])) >= max_cycles:
        reasons.append(f"max_codex_cycles reached: {max_cycles}")
    max_phase_visits = config.get("max_phase_visits")
    if isinstance(max_phase_visits, int) and current_phase != "complete":
        visits = phase_visit_count(state, current_phase)
        if visits > max_phase_visits:
            reasons.append(f"phase {current_phase} exceeded max_phase_visits={max_phase_visits}")
    pause_before = config.get("pause_before_phases")
    if isinstance(pause_before, list) and current_phase in {str(item) for item in pause_before}:
        reasons.append(f"configured pause before phase {current_phase}")
    if current_phase == "complete" and config.get("stop_when_complete", True):
        reasons.append("workflow is complete")
    success = success_status(root, state, config)
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "should_stop": bool(reasons),
        "reasons": reasons,
        "current_phase": current_phase,
        "success": success,
        "config_path": STOP_CONDITIONS_FILE,
    }

