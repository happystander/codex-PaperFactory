#!/usr/bin/env python3
"""Smoke tests for the interactive PaperFactory Web UI."""

from __future__ import annotations

import json
import os
import shutil
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
    assert paperfactory_web.project_slug("全模态 生成式推荐!") == "全模态-生成式推荐"
    assert "轮数" in paperfactory_web.finished_job_message({"command": ["paperfactory", "run", "--cycles", "1"]})

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
        created_project_dir: Path | None = None
        try:
            index = fetch_text(base + "/")
            assert "PaperFactory" in index
            assert "运行状态" in index
            assert "Codex 现在在做什么" in index
            assert "研究任务" in index
            assert "新建并切换" in index
            assert "留空=持续" in index
            assert "默认持续运行" in index
            assert "文件树" in index
            assert "treeFolder" in index
            assert "buildFileTree" in index
            assert "阶段路由" in index
            assert "保存流程" in index
            assert "主干阶段固定" in index
            assert "添加阶段" in index
            assert "自定义方法/阶段" in index
            assert "标准记忆" in index
            assert "formatMessageTime" in index
            assert "${t('time')} ${time}" in index
            assert "运行时控制" in index
            assert "runtimeDetails" in index
            assert "GPU 状态" in index
            assert "gpuGrid" in index
            assert "langZhBtn" in index
            assert "langEnBtn" in index
            assert "User-facing language" not in index
            assert "What Codex Is Doing" in index

            status = fetch_json(base + "/api/status")
            assert status["phase"]["key"] == "scope"
            assert status["phase"]["display_status"]
            assert status["phase"]["page_url"] == "/phase?key=scope"
            assert status["job"]["running"] is False
            assert status["job"]["health"] == "idle"
            assert status["job"]["state_label"]
            assert "gpu" in status
            assert "health" in status["gpu"]
            gpu_status = fetch_json(base + "/api/gpu/status")
            assert "checked_at" in gpu_status

            phase_page = fetch_text(base + "/phase?key=scope")
            assert "Research Scope" in phase_page
            assert "必需产物" in phase_page

            ui = fetch_json(base + "/api/ui-config")
            assert ui["language"] == "zh"
            ui = fetch_json(base + "/api/ui-config", {"language": "en"})
            assert ui["language"] == "en"
            phase_page_en = fetch_text(base + "/phase?key=scope")
            assert '<html lang="en">' in phase_page_en
            assert "Back to Console" in phase_page_en
            prompt_en = fetch_json(base + "/api/prompt", {})
            assert "User-facing language: English." in prompt_en["prompt"]
            review_prompt_en = fetch_json(base + "/api/review/prompt", {})
            assert "User-facing language: English." in review_prompt_en["prompt"]
            ui = fetch_json(base + "/api/ui-config", {"language": "zh"})
            assert ui["language"] == "zh"
            prompt_zh = fetch_json(base + "/api/prompt", {})
            assert "User-facing language: Simplified Chinese." in prompt_zh["prompt"]
            assert "GPU resource snapshot:" in prompt_zh["prompt"]
            assert (root / "ui_config.json").exists()

            workflow = fetch_json(base + "/api/workflow")
            assert workflow["phases"][0]["key"] == "scope"
            assert workflow["phases"][0]["kind"] == "base"
            assert workflow["phases"][0]["locked"] is True
            saved_workflow = fetch_json(
                base + "/api/workflow",
                {
                    "phases": [
                        {
                            "kind": "custom",
                            "key": "custom_user_checkpoint",
                            "title": "用户补充检查",
                            "insert_after": "scope",
                            "prompt": "检查范围阶段是否遗漏用户指定约束。",
                            "enabled": True,
                        }
                    ]
                },
            )
            assert saved_workflow["phases"][0]["title"] == "Research Scope"
            assert saved_workflow["phases"][1]["key"] == "custom_user_checkpoint"
            assert saved_workflow["phases"][1]["kind"] == "custom"
            status = fetch_json(base + "/api/status")
            assert status["phases"][1]["title"] == "用户补充检查"
            custom_page = fetch_text(base + "/phase?key=custom_user_checkpoint")
            assert "自定义 Prompt" in custom_page
            assert "检查范围阶段是否遗漏用户指定约束" in custom_page
            reset_workflow = fetch_json(base + "/api/workflow", {"reset": True})
            assert reset_workflow["phases"][0]["title"] == "Research Scope"
            assert all(item["kind"] == "base" for item in reset_workflow["phases"])

            state = researchctl.load_state(root)
            state["phase"] = "method_design"
            state["phase_history"] = [
                {"phase": "scope", "completed_at": "2026-05-12T09:00:00+00:00"},
                {"phase": "survey", "completed_at": "2026-05-12T10:00:00+00:00"},
                {"phase": "method_design", "completed_at": "2026-05-12T11:00:00+00:00"},
            ]
            state["phase_routes"] = [
                {
                    "decision": "jump_back",
                    "from_phase": "method_smoke",
                    "target_phase": "method_design",
                    "resolved_next_phase": "method_design",
                    "reason": "smoke test exposed a weak ablation plan",
                    "confidence": 0.8,
                    "decided_at": "2026-05-12T12:00:00+00:00",
                },
                {
                    "decision": "repeat",
                    "from_phase": "method_design",
                    "target_phase": "",
                    "resolved_next_phase": "method_design",
                    "reason": "method design still needs another pass",
                    "confidence": 0.7,
                    "decided_at": "2026-05-12T13:00:00+00:00",
                },
            ]
            researchctl.write_state(root, state)
            routed = fetch_json(base + "/api/status")
            assert routed["phase"]["key"] == "method_design"
            assert routed["phase"]["revisited"] is True
            assert routed["phase"]["active_visit_count"] == 2
            assert routed["route_summary"]["total"] == 2
            assert routed["route_summary"]["jumps"] == 2
            assert routed["routes"][0]["decision"] == "jump_back"
            assert routed["routes"][1]["decision"] == "repeat"

            projects = fetch_json(base + "/api/projects")
            assert any(item["research_dir"] == str(root) and item["current"] for item in projects["projects"])
            assert all("running" in item for item in projects["projects"])
            created = fetch_json(
                base + "/api/project/create",
                {"task": "parallel web smoke research direction", "name": "parallel-ui-smoke"},
            )
            created_project_dir = Path(created["created_project"]["project_dir"])
            created_root = Path(created["created_project"]["research_dir"])
            assert created_root.exists()
            assert created["phase"]["key"] == "scope"
            assert created["created_project"]["name"].endswith("parallel-ui-smoke")
            assert "parallel web smoke research direction" in (created_root / "task.md").read_text(encoding="utf-8")
            assert any(item["research_dir"] == str(created_root) and item["current"] for item in created["projects"])
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
            assert (root / "interventions" / "patches.jsonl").exists()

            runtime = fetch_json(base + "/api/runtime")
            assert runtime["workflow"]["current_phase"] == "method_design"
            assert "gpu" in runtime
            assert runtime["workflow"]["nodes"]
            assert runtime["queue"]["counts"]["pending"] >= 1
            assert runtime["queue"]["next_task"]
            assert "paper_safe_claims" in runtime["evidence"]["summary"]
            assert runtime["control"]["decision"]["current_phase"] == "method_design"
            assert runtime["interventions"]["pending_count"] >= 1
            assert (root / "workflow_state.json").exists()
            assert (root / "evidence" / "registry.json").exists()
            assert (root / "queue" / "tasks.jsonl").exists()
            assert (root / "control" / "stop_conditions.json").exists()

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
            assert all("ts" in item for item in stream["messages"])

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
            if created_project_dir is not None:
                shutil.rmtree(created_project_dir, ignore_errors=True)

    print("paperfactory web smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
