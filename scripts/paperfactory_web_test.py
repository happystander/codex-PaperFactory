#!/usr/bin/env python3
"""Smoke tests for the interactive PaperFactory Web UI."""

from __future__ import annotations

import json
import os
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
            assert "运行状态" in index
            assert "Codex 现在在做什么" in index
            assert "研究任务" in index
            assert "文件树" in index
            assert "保存流程" in index
            assert "标准记忆" in index

            status = fetch_json(base + "/api/status")
            assert status["phase"]["key"] == "scope"
            assert status["phase"]["display_status"]
            assert status["phase"]["page_url"] == "/phase?key=scope"
            assert status["job"]["running"] is False
            assert status["job"]["health"] == "idle"
            assert status["job"]["state_label"]

            phase_page = fetch_text(base + "/phase?key=scope")
            assert "Research Scope" in phase_page
            assert "必需产物" in phase_page

            workflow = fetch_json(base + "/api/workflow")
            assert workflow["phases"][0]["key"] == "scope"
            edited = dict(workflow)
            edited["phases"] = [dict(item) for item in workflow["phases"]]
            edited["phases"][0]["title"] = "自定义范围"
            edited["phases"][1], edited["phases"][2] = edited["phases"][2], edited["phases"][1]
            saved_workflow = fetch_json(base + "/api/workflow", edited)
            assert saved_workflow["phases"][0]["title"] == "自定义范围"
            status = fetch_json(base + "/api/status")
            assert status["phases"][0]["title"] == "自定义范围"
            reset_workflow = fetch_json(base + "/api/workflow", {"reset": True})
            assert reset_workflow["phases"][0]["title"] == "Research Scope"

            projects = fetch_json(base + "/api/projects")
            assert any(item["research_dir"] == str(root) and item["current"] for item in projects["projects"])
            switched = fetch_json(base + "/api/project/switch", {"research_dir": str(root)})
            assert switched["research_dir"] == str(root)

            session = Path(tmp) / ".codex" / "sessions" / "2026" / "05" / "12" / "rollout-test.jsonl"
            session.parent.mkdir(parents=True, exist_ok=True)
            session.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-05-12T09:00:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "model_context_window": 258400,
                                "total_token_usage": {"total_tokens": 12345, "input_tokens": 10000},
                                "last_token_usage": {"total_tokens": 456, "output_tokens": 123},
                            },
                            "rate_limits": {
                                "plan_type": "prolite",
                                "primary": {"used_percent": 25.5, "window_minutes": 300, "resets_at": 1778593065},
                                "secondary": {"used_percent": 60, "window_minutes": 10080, "resets_at": 1778639106},
                            },
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                codex = fetch_json(base + "/api/codex/status")
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home
            assert codex["available"] is True
            assert codex["source"] == "latest"
            assert codex["plan_type"] == "prolite"
            assert codex["primary"]["remaining_percent"] == 74.5
            assert codex["secondary"]["remaining_percent"] == 40.0
            assert codex["model_context_window"] == 258400

            fetch_json(base + "/api/task", {"task": "updated web smoke task"})
            status = fetch_json(base + "/api/status")
            assert status["task"] == "updated web smoke task"

            prompt = fetch_json(base + "/api/prompt", {})
            assert "updated web smoke task" in prompt["prompt"]
            assert "progress/feed.jsonl" in prompt["prompt"]
            assert (root / "next_prompt.md").exists()
            preview = fetch_text(base + "/preview?path=next_prompt.md")
            assert "updated web smoke task" in preview

            intervention = fetch_json(base + "/api/intervention", {"message": "人工要求：优先检查引用真实性。"})
            assert intervention["ok"] is True
            assert "优先检查引用真实性" in intervention["prompt"]
            assert (root / "human_interventions.md").exists()

            memory = fetch_json(base + "/api/memory")
            assert memory["summary"] is True
            assert memory["profile"]
            memory = fetch_json(base + "/api/memory", {"profile": "focused"})
            assert memory["profile"] == "focused"
            assert memory["logs"] is False
            memory = fetch_json(base + "/api/memory", {"profile": "custom", "logs": False, "artifact_index": False})
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
            assert "last_activity" in status["job"]

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
