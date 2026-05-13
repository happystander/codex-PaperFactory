#!/usr/bin/env python3
"""Smoke tests for researchctl.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CTL = ROOT / "scripts" / "researchctl.py"


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CTL), *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        rd = cwd / ".research"
        proc = run(["--research-dir", str(rd), "init", "--task", "test task"], cwd)
        assert proc.returncode == 0, proc.stderr
        assert (rd / "state.json").exists()
        assert (rd / "archive" / "cleanup").is_dir()
        assert (rd / "memory" / "handoff.md").exists()
        assert (rd / "memory" / "global_memory.md").exists()
        assert (rd / "memory" / "phase_memory.md").exists()
        assert (rd / "memory" / "artifact_index.json").exists()
        assert (rd / "workflow_state.json").exists()
        assert (rd / "evidence" / "registry.json").exists()
        assert (rd / "queue" / "tasks.jsonl").exists()
        assert (rd / "control" / "stop_conditions.json").exists()
        (rd / "workflow.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "custom_phases": [
                        {
                            "key": "custom_protocol_review",
                            "title": "Protocol Review",
                            "insert_after": "scope",
                            "prompt": "Review the scope for protocol holes before survey.",
                            "enabled": True,
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        proc = run(["--research-dir", str(rd), "status"], cwd)
        assert proc.returncode == 0, proc.stderr
        assert "Phase: scope" in proc.stdout

        proc = run(["--research-dir", str(rd), "next-prompt"], cwd)
        assert proc.returncode == 0, proc.stderr
        assert "cleanup pass" in proc.stdout
        assert ".research/archive/cleanup/scope/" in proc.stdout
        assert ".research/memory/handoff.md" in proc.stdout
        assert ".research/workflow_state.json" in proc.stdout
        assert ".research/evidence/registry.json" in proc.stdout
        assert ".research/queue/tasks.jsonl" in proc.stdout
        assert "execute -> self-check -> repair -> evidence-check -> report -> route decision" in proc.stdout
        assert "Memory Contract" in (rd / "memory" / "handoff.md").read_text(encoding="utf-8")

        proc = run(["--research-dir", str(rd), "advance"], cwd)
        assert proc.returncode == 1
        assert "cannot advance" in proc.stdout

        (rd / "scope").mkdir(exist_ok=True)
        (rd / "reports").mkdir(exist_ok=True)
        (rd / "scope" / "research_scope.md").write_text("scope\n", encoding="utf-8")
        (rd / "reports" / "scope.json").write_text(
            json.dumps(
                {
                    "phase": "scope",
                    "status": "complete",
                    "summary": "The scoped task is evidence-testable.",
                    "claims": ["The scoped task is evidence-testable."],
                    "evidence": ["scope/research_scope.md"],
                    "commands": ["manual scope review"],
                    "self_check": {
                        "executed": ["scope review"],
                        "issues": [],
                        "repairs": [],
                        "evidence_checked": ["scope/research_scope.md"],
                        "review_gate": "scope_consistency_review",
                        "review_result": "pass",
                    },
                    "route": {"decision": "advance", "confidence": 0.8},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        proc = run(["--research-dir", str(rd), "advance"], cwd)
        assert proc.returncode == 0, proc.stderr
        state = json.loads((rd / "state.json").read_text(encoding="utf-8"))
        assert state["phase"] == "custom_protocol_review"
        assert "scope" in (rd / "memory" / "phase_summaries.jsonl").read_text(encoding="utf-8")
        registry = json.loads((rd / "evidence" / "registry.json").read_text(encoding="utf-8"))
        assert registry["summary"]["claims_verified"] >= 1
        workflow_state = json.loads((rd / "workflow_state.json").read_text(encoding="utf-8"))
        assert workflow_state["nodes"][0]["entry_condition"]
        assert workflow_state["nodes"][0]["review_gate"] == "scope_consistency_review"

        proc = run(["--research-dir", str(rd), "memory", "--json"], cwd)
        assert proc.returncode == 0, proc.stderr
        memory_payload = json.loads(proc.stdout)
        assert memory_payload["reports"] == 1
        assert memory_payload["artifacts"] >= 3
        assert memory_payload["layered_memory"] is True

        proc = run(["--research-dir", str(rd), "runtime", "--json"], cwd)
        assert proc.returncode == 0, proc.stderr
        runtime_payload = json.loads(proc.stdout)
        assert runtime_payload["workflow"]["nodes"] >= 10
        assert "counts" in runtime_payload["queue"]

        proc = run(["--research-dir", str(rd), "intervention", "--message", "请调整 stop condition", "--json"], cwd)
        assert proc.returncode == 0, proc.stderr
        patch = json.loads(proc.stdout)
        assert patch["kind"] == "stop_condition"
        assert (rd / "interventions" / "patches.jsonl").exists()

        proc = run(["--research-dir", str(rd), "next-prompt"], cwd)
        assert proc.returncode == 0, proc.stderr
        assert "Review the scope for protocol holes before survey" in proc.stdout

        (rd / "custom").mkdir(exist_ok=True)
        (rd / "custom" / "custom_protocol_review.md").write_text("custom review\n", encoding="utf-8")
        (rd / "reports" / "custom_protocol_review.json").write_text(
            json.dumps(
                {
                    "phase": "custom_protocol_review",
                    "status": "complete",
                    "self_check": {
                        "executed": ["custom review"],
                        "issues": [],
                        "repairs": [],
                        "evidence_checked": ["custom/custom_protocol_review.md"],
                        "review_gate": "custom_phase_self_review",
                        "review_result": "pass",
                    },
                    "route": {
                        "decision": "skip_next",
                        "reason": "survey was already covered by the inserted review fixture",
                        "confidence": 0.7,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        proc = run(["--research-dir", str(rd), "advance"], cwd)
        assert proc.returncode == 0, proc.stderr
        state = json.loads((rd / "state.json").read_text(encoding="utf-8"))
        assert state["phase"] == "data_sanity"
        assert state["phase_routes"][-1]["decision"] == "skip_next"

        proc = run(["--research-dir", str(rd), "validate"], cwd)
        assert proc.returncode == 0, proc.stderr

        state = json.loads((rd / "state.json").read_text(encoding="utf-8"))
        state["phase"] = "survey"
        (rd / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        proc = run(["--research-dir", str(rd), "next-prompt"], cwd)
        assert proc.returncode == 0, proc.stderr
        assert "literature/paper_priority_scores.json" in proc.stdout
        assert "literature/claim_extraction.json" in proc.stdout
        assert "literature/code_interface_map.md" in proc.stdout

        state["phase"] = "method_design"
        (rd / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        for rel in (
            "method/atomic_concepts.md",
            "method/nearest_prior_diff.md",
            "method/candidate_methods.json",
            "method/idea_critic.md",
            "method/method_design.md",
            "method/implementation_plan.md",
            "experiments/method_smoke/plan.md",
        ):
            path = rd / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n", encoding="utf-8")
        (rd / "method" / "novelty_risk.json").write_text(
            json.dumps(
                {
                    "novelty_risk_score": 0.9,
                    "risk_level": "high",
                    "overlap_types": ["parameter_tuning"],
                    "pass_to_smoke": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (rd / "reports" / "method_design.json").write_text(
            json.dumps(
                {
                    "phase": "method_design",
                    "status": "complete",
                    "self_check": {"review_gate": "method_innovation_review", "review_result": "pass"},
                    "route": {"decision": "advance", "confidence": 0.8},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        proc = run(["--research-dir", str(rd), "advance"], cwd)
        assert proc.returncode == 1
        assert "pass_to_smoke is not true" in proc.stdout
        assert "parameter_tuning" in proc.stdout

        (rd / "method" / "novelty_risk.json").write_text(
            json.dumps(
                {
                    "novelty_risk_score": 0.2,
                    "risk_level": "low",
                    "overlap_types": [],
                    "missing_evidence": [],
                    "required_repairs": [],
                    "pass_to_smoke": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        proc = run(["--research-dir", str(rd), "advance"], cwd)
        assert proc.returncode == 0, proc.stderr
        assert "method_design -> method_smoke" in proc.stdout

    print("researchctl smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
