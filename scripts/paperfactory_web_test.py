#!/usr/bin/env python3
"""Smoke tests for the interactive PaperFactory Web UI."""

from __future__ import annotations

import json
import stat
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import paperfactory_web
import researchctl


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch_json(url: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"content-type": "application/json"})
    with OPENER.open(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    with OPENER.open(url, timeout=10) as response:
        return response.read().decode("utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / ".research"
        researchctl.command_init(
            type("Args", (), {"research_dir": str(root), "task": "web smoke task", "force": False})()
        )
        manager = paperfactory_web.JobManager()
        server = ThreadingHTTPServer(("127.0.0.1", 0), paperfactory_web.make_handler(root, manager))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            index = fetch_text(base + "/")
            assert "PaperFactory" in index
            assert "Codex 进展" in index
            assert "文件树" in index

            status = fetch_json(base + "/api/status")
            assert status["phase"]["key"] == "scope"
            assert status["job"]["running"] is False

            fetch_json(base + "/api/task", {"task": "updated web smoke task"})
            status = fetch_json(base + "/api/status")
            assert status["task"] == "updated web smoke task"

            prompt = fetch_json(base + "/api/prompt", {})
            assert "updated web smoke task" in prompt["prompt"]
            assert "progress/feed.jsonl" in prompt["prompt"]
            assert (root / "next_prompt.md").exists()

            intervention = fetch_json(base + "/api/intervention", {"message": "人工要求：优先检查引用真实性。"})
            assert intervention["ok"] is True
            assert "优先检查引用真实性" in intervention["prompt"]
            assert (root / "human_interventions.md").exists()

            memory = fetch_json(base + "/api/memory")
            assert memory["summary"] is True
            memory = fetch_json(base + "/api/memory", {"logs": False, "artifact_index": False})
            assert memory["logs"] is False
            assert memory["artifact_index"] is False

            start = fetch_json(base + "/api/run/start", {"cycles": 1, "interval": 1, "dry_run": True})
            assert start["ok"] is True
            for _ in range(20):
                status = fetch_json(base + "/api/status")
                if not status["job"]["running"]:
                    break
                time.sleep(0.1)
            assert status["job"]["running"] is False
            assert status["job"]["completed"] == 1
            assert status["job"]["detached"] is True

            artifacts = fetch_json(base + "/api/artifacts")
            assert any(item["path"] == "next_prompt.md" for item in artifacts["files"])
            tree = fetch_json(base + "/api/tree")
            assert any(item["path"] == "next_prompt.md" for item in tree["files"])
            stream = fetch_json(base + "/api/stream?limit=80")
            assert any("优先检查引用真实性" in item["text"] for item in stream["messages"])

            fake_codex = Path(tmp) / "fake_codex.sh"
            fake_codex.write_text("#!/usr/bin/env bash\necho fake codex visible output\nsleep 8\n", encoding="utf-8")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
            start = fetch_json(
                base + "/api/run/start",
                {"cycles": 1, "interval": 1, "dry_run": False, "codex_bin": str(fake_codex)},
            )
            assert start["ok"] is True
            status = fetch_json(base + "/api/status")
            assert status["job"]["running"] is True
            assert status["job"]["current_pid"]
            stopped = fetch_json(base + "/api/run/stop", {})
            assert stopped["ok"] is True
            for _ in range(20):
                status = fetch_json(base + "/api/status")
                if not status["job"]["running"]:
                    break
                time.sleep(0.1)
            assert status["job"]["running"] is False
        finally:
            manager.stop()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    print("paperfactory web smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
