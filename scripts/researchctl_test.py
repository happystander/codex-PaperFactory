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

        proc = run(["--research-dir", str(rd), "advance"], cwd)
        assert proc.returncode == 1
        assert "cannot advance" in proc.stdout

        (rd / "scope").mkdir(exist_ok=True)
        (rd / "reports").mkdir(exist_ok=True)
        (rd / "scope" / "research_scope.md").write_text("scope\n", encoding="utf-8")
        (rd / "reports" / "scope.json").write_text(
            json.dumps({"phase": "scope", "status": "complete"}) + "\n",
            encoding="utf-8",
        )
        proc = run(["--research-dir", str(rd), "advance"], cwd)
        assert proc.returncode == 0, proc.stderr
        state = json.loads((rd / "state.json").read_text(encoding="utf-8"))
        assert state["phase"] == "custom_protocol_review"

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

    print("researchctl smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
