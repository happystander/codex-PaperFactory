#!/usr/bin/env python3
"""Smoke tests for the PaperFactory convenience launcher."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "paperfactory.py"


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
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

        proc = run(["new", "--research-dir", str(rd), "--task", "launcher smoke task"], cwd)
        assert proc.returncode == 0, proc.stderr
        assert (rd / "state.json").exists()
        assert (rd / "next_prompt.md").exists()
        assert (rd / "dashboard.html").exists()
        assert (rd / "workflow_state.json").exists()
        assert (rd / "evidence" / "registry.json").exists()
        assert (rd / "queue" / "tasks.jsonl").exists()

        proc = run(["status", "--research-dir", str(rd), "--json"], cwd)
        assert proc.returncode == 0, proc.stderr
        status = json.loads(proc.stdout)
        assert status["phase"] == "scope"
        assert status["progress"]["total"] == 10

        proc = run(["prompt", "--research-dir", str(rd)], cwd)
        assert proc.returncode == 0, proc.stderr
        assert "Wrote next prompt" in proc.stdout

        proc = run(["runtime", "--research-dir", str(rd), "--json"], cwd)
        assert proc.returncode == 0, proc.stderr
        runtime = json.loads(proc.stdout)
        assert runtime["workflow"]["nodes"] == 10

        proc = run(["queue", "--research-dir", str(rd), "--json"], cwd)
        assert proc.returncode == 0, proc.stderr
        queue = json.loads(proc.stdout)
        assert queue["counts"]["pending"] >= 1

        proc = run(["control", "--research-dir", str(rd), "--json"], cwd)
        assert proc.returncode == 0, proc.stderr
        control = json.loads(proc.stdout)
        assert control["should_stop"] is False

        proc = run(["dashboard", "--research-dir", str(rd)], cwd)
        assert proc.returncode == 0, proc.stderr
        assert "Wrote dashboard" in proc.stdout

        proc = run(["log", "--research-dir", str(rd), "--action", "launcher test", "--outcome", "ok"], cwd)
        assert proc.returncode == 0, proc.stderr
        assert "launcher test" in (rd / "logs" / "research.log").read_text(encoding="utf-8")

        proc = run(["run", "--research-dir", str(rd), "--once", "--dry-run"], cwd)
        assert proc.returncode == 0, proc.stderr
        assert "Dry run" in proc.stdout

        fake_codex = cwd / "fake_codex.sh"
        fake_codex.write_text("#!/usr/bin/env bash\nprintf 'FAKE_CODEX_CWD=%s\\n' \"$PWD\"\n", encoding="utf-8")
        fake_codex.chmod(0o755)
        proc = run(["run", "--research-dir", str(rd), "--once", "--codex-bin", str(fake_codex)], ROOT)
        assert proc.returncode == 0, proc.stderr
        codex_log = (rd / "logs" / "codex-loop.out").read_text(encoding="utf-8")
        assert f"Codex workdir: {cwd}" in codex_log
        assert f"FAKE_CODEX_CWD={cwd}" in codex_log

    print("paperfactory launcher smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
