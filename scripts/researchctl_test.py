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

        proc = run(["--research-dir", str(rd), "status"], cwd)
        assert proc.returncode == 0, proc.stderr
        assert "Phase: scope" in proc.stdout

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
        assert state["phase"] == "survey"

        proc = run(["--research-dir", str(rd), "validate"], cwd)
        assert proc.returncode == 0, proc.stderr

    print("researchctl smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
