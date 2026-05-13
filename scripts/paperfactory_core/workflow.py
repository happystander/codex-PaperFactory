"""Workflow state-machine view for PaperFactory phases."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


WORKFLOW_STATE_FILE = "workflow_state.json"
DEFAULT_ALLOWED_ROUTES = ("advance", "repeat", "jump_back", "jump_to", "skip_next")
CUSTOM_ALLOWED_ROUTES = ("advance", "repeat", "jump_back", "jump_to", "skip_next", "skip_to")

PHASE_POLICIES: dict[str, dict[str, Any]] = {
    "scope": {
        "entry_condition": "Initial task exists and scope has not been accepted.",
        "failure_policy": "repeat until the problem, exclusions, metrics, budget, and success criteria are explicit.",
        "retry_budget": 3,
        "max_runtime_hours": 2,
        "review_gate": "scope_consistency_review",
        "memory_inputs": ("global_memory", "human_interventions"),
        "allowed_routes": ("advance", "repeat", "jump_to"),
    },
    "survey": {
        "entry_condition": "Scope is complete.",
        "failure_policy": "jump_back to scope if the novelty gap changes the target; otherwise repeat survey.",
        "retry_budget": 4,
        "max_runtime_hours": 12,
        "review_gate": "novelty_and_baseline_review",
        "memory_inputs": ("global_memory", "phase_memory", "decision_memory", "negative_memory"),
    },
    "data_sanity": {
        "entry_condition": "Survey identifies datasets, metrics, and protocol constraints.",
        "failure_policy": "jump_back to survey when no valid dataset/protocol exists; otherwise repeat.",
        "retry_budget": 3,
        "max_runtime_hours": 6,
        "review_gate": "data_protocol_review",
        "memory_inputs": ("global_memory", "phase_memory", "risk_memory"),
    },
    "cheap_baselines": {
        "entry_condition": "Data protocol is explicit.",
        "failure_policy": "repeat with simpler baselines; jump_back to data_sanity if protocol blocks evaluation.",
        "retry_budget": 4,
        "max_runtime_hours": 12,
        "review_gate": "baseline_floor_review",
        "memory_inputs": ("phase_memory", "evidence_registry", "task_queue"),
    },
    "method_design": {
        "entry_condition": "Baseline floor and novelty gap are known.",
        "failure_policy": "jump_back to survey or cheap_baselines if the idea is not distinct or testable.",
        "retry_budget": 4,
        "max_runtime_hours": 8,
        "review_gate": "innovation_falsifiability_review",
        "memory_inputs": ("global_memory", "decision_memory", "negative_memory", "evidence_registry"),
    },
    "method_smoke": {
        "entry_condition": "Implementation plan and smoke protocol exist.",
        "failure_policy": "repeat after repair; jump_back to method_design when the core mechanism fails.",
        "retry_budget": 5,
        "max_runtime_hours": 24,
        "review_gate": "smoke_signal_review",
        "memory_inputs": ("phase_memory", "task_queue", "evidence_registry", "negative_memory"),
    },
    "advanced_comparison": {
        "entry_condition": "Smoke test shows a credible signal or clearly justified diagnostic path.",
        "failure_policy": "repeat for fair-comparison repair; jump_back to method_smoke if signal vanishes.",
        "retry_budget": 5,
        "max_runtime_hours": 48,
        "review_gate": "fair_comparison_review",
        "memory_inputs": ("task_queue", "evidence_registry", "decision_memory", "negative_memory"),
    },
    "paper_evidence": {
        "entry_condition": "Experiments and comparisons produce paper-ready evidence or scoped negative findings.",
        "failure_policy": "jump_back to the weakest evidence phase; do not draft around missing evidence.",
        "retry_budget": 3,
        "max_runtime_hours": 10,
        "review_gate": "claim_support_review",
        "memory_inputs": ("evidence_registry", "writing_memory", "negative_memory"),
    },
    "paper_drafting": {
        "entry_condition": "Claim-support evidence exists.",
        "failure_policy": "jump_back to paper_evidence for unsupported claims; repeat for writing repair.",
        "retry_budget": 4,
        "max_runtime_hours": 16,
        "review_gate": "paper_structure_review",
        "memory_inputs": ("writing_memory", "evidence_registry", "best_paper_references"),
    },
    "internal_review": {
        "entry_condition": "Draft, appendix, bibliography, and claim map exist.",
        "failure_policy": "jump_back to the phase named by the blocking review issue.",
        "retry_budget": 4,
        "max_runtime_hours": 12,
        "review_gate": "top_conference_adversarial_review",
        "memory_inputs": ("writing_memory", "evidence_registry", "risk_memory", "negative_memory"),
    },
}


def iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def policy_for_phase(phase: Any) -> dict[str, Any]:
    if getattr(phase, "kind", "base") == "custom":
        return {
            "entry_condition": "Custom phase was reached by the configured workflow.",
            "failure_policy": "repeat, jump_back, or skip according to the custom prompt and evidence safety.",
            "retry_budget": 3,
            "max_runtime_hours": 6,
            "review_gate": "custom_phase_self_review",
            "memory_inputs": ("global_memory", "phase_memory", "human_interventions", "task_queue"),
            "allowed_routes": CUSTOM_ALLOWED_ROUTES,
        }
    policy = dict(PHASE_POLICIES.get(getattr(phase, "key", ""), {}))
    policy.setdefault("entry_condition", "Previous phase gate is complete.")
    policy.setdefault("failure_policy", "repeat or route to the phase that can repair the blocking issue.")
    policy.setdefault("retry_budget", 3)
    policy.setdefault("max_runtime_hours", 8)
    policy.setdefault("review_gate", "phase_self_review")
    policy.setdefault("memory_inputs", ("global_memory", "phase_memory"))
    policy.setdefault("allowed_routes", DEFAULT_ALLOWED_ROUTES)
    return policy


def route_allowed(phase: Any, decision: str) -> bool:
    return decision in set(policy_for_phase(phase).get("allowed_routes") or DEFAULT_ALLOWED_ROUTES)


def phase_visit_count(state: dict[str, Any], key: str) -> int:
    count = 1 if state.get("phase") == key else 0
    for item in state.get("phase_history", []):
        if isinstance(item, dict) and item.get("phase") == key:
            count += 1
    return count


def build_state_machine(
    phases: tuple[Any, ...],
    state: dict[str, Any],
    *,
    report_statuses: dict[str, str | None],
    missing_by_phase: dict[str, list[str]],
) -> dict[str, Any]:
    current_key = str(state.get("phase") or "")
    phase_keys = [getattr(phase, "key", "") for phase in phases]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    completed = {item.get("phase") for item in state.get("phase_history", []) if isinstance(item, dict)}
    for index, phase in enumerate(phases):
        key = getattr(phase, "key", "")
        policy = policy_for_phase(phase)
        if current_key == "complete" or key in completed:
            status = "complete"
        elif key == current_key:
            status = "active"
        else:
            status = "pending"
        nodes.append(
            {
                "key": key,
                "title": getattr(phase, "title", key),
                "kind": getattr(phase, "kind", "base"),
                "status": status,
                "index": index + 1,
                "entry_condition": policy["entry_condition"],
                "exit_gate": getattr(phase, "gate", ""),
                "failure_policy": policy["failure_policy"],
                "retry_budget": policy["retry_budget"],
                "visits": phase_visit_count(state, key),
                "max_runtime_hours": policy["max_runtime_hours"],
                "review_gate": policy["review_gate"],
                "required_memory_inputs": list(policy["memory_inputs"]),
                "allowed_routes": list(policy["allowed_routes"]),
                "report_status": report_statuses.get(key),
                "missing": missing_by_phase.get(key, []),
            }
        )
        if index + 1 < len(phases):
            edges.append({"from": key, "to": phase_keys[index + 1], "route": "advance"})
        edges.append({"from": key, "to": key, "route": "repeat"})
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "current_phase": current_key,
        "nodes": nodes,
        "edges": edges,
        "route_history": state.get("phase_routes", [])[-50:],
    }


def write_state_machine(
    root: Path,
    phases: tuple[Any, ...],
    state: dict[str, Any],
    *,
    report_statuses: dict[str, str | None],
    missing_by_phase: dict[str, list[str]],
) -> dict[str, Any]:
    payload = build_state_machine(
        phases,
        state,
        report_statuses=report_statuses,
        missing_by_phase=missing_by_phase,
    )
    path = root / WORKFLOW_STATE_FILE
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload

