#!/usr/bin/env python3
"""Interactive local Web UI for Codex PaperFactory."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import researchctl


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {
    ".bib",
    ".cfg",
    ".csv",
    ".json",
    ".log",
    ".md",
    ".py",
    ".sh",
    ".tex",
    ".toml",
    ".tsv",
    ".txt",
    ".typ",
    ".yaml",
    ".yml",
}
FIGURE_EXTENSIONS = {".svg", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}
JOB_FILE = "web_job.json"
HUMAN_INTERVENTIONS = "human_interventions.md"
MEMORY_CONFIG = "memory_config.json"
PROGRESS_FEED = "progress/feed.jsonl"
MEMORY_PROFILES: dict[str, dict[str, Any]] = {
    "focused": {
        "label": "轻量记忆",
        "description": "适合快速迭代：只带研究摘要和人工介入，减少旧信息干扰。",
        "config": {"summary": True, "logs": False, "human_interventions": True, "artifact_index": False},
    },
    "balanced": {
        "label": "标准记忆",
        "description": "推荐：带研究摘要、人工介入和当前阶段产物，让 Codex 保持上下文但不过载。",
        "config": {"summary": True, "logs": False, "human_interventions": True, "artifact_index": True},
    },
    "deep": {
        "label": "深度记忆",
        "description": "适合排错或长链路恢复：带摘要、运行记录、人工介入和当前产物。",
        "config": {"summary": True, "logs": True, "human_interventions": True, "artifact_index": True},
    },
    "clean": {
        "label": "干净启动",
        "description": "只保留任务本身和人工介入，适合想让 Codex 少受历史影响时使用。",
        "config": {"summary": False, "logs": False, "human_interventions": True, "artifact_index": False},
    },
}


def now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("content-length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def safe_rel_path(raw: str) -> Path:
    rel = Path(urllib.parse.unquote(raw))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Invalid relative path")
    return rel


def file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in FIGURE_EXTENSIONS:
        return "figure"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    return "file"


def file_entry(root: Path, path: Path) -> dict[str, Any]:
    rel = path.relative_to(root).as_posix()
    stat = path.stat()
    return {
        "path": rel,
        "name": path.name,
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "kind": file_kind(path),
        "url": f"/files/{urllib.parse.quote(rel)}",
    }


def file_tree(root: Path, max_files: int = 240) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    files = [path for path in root.rglob("*") if path.is_file()]
    files.sort(key=lambda path: path.relative_to(root).as_posix())
    for path in files[:max_files]:
        rel = path.relative_to(root)
        rows.append(
            {
                "path": rel.as_posix(),
                "name": path.name,
                "depth": max(0, len(rel.parts) - 1),
                "kind": file_kind(path),
                "size": path.stat().st_size,
                "url": f"/files/{urllib.parse.quote(rel.as_posix())}",
            }
        )
    return rows


def normalize_research_root(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path.name != ".research" and researchctl.state_path(path / ".research").exists():
        path = path / ".research"
    if not researchctl.state_path(path).exists():
        raise ValueError(f"Research state not found: {researchctl.state_path(path)}")
    return path


def workspace_for(root: Path) -> Path:
    current = normalize_research_root(root)
    if current.name == ".research":
        return current.parent.parent
    return current.parent


def project_slug(text: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text.strip().lower(), flags=re.UNICODE).strip("-_")
    slug = re.sub(r"-{2,}", "-", slug)[:48].strip("-_")
    return slug or "research"


def unique_project_dir(workspace: Path, task: str, name: str = "") -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    slug = project_slug(name or task)
    base = f"{stamp}-{slug}"
    candidate = workspace / base
    suffix = 2
    while candidate.exists():
        candidate = workspace / f"{base}-{suffix}"
        suffix += 1
    return candidate


def project_job_summary(root: Path) -> dict[str, Any]:
    job = read_job(root)
    pid = int(job.get("pid") or 0) if job else 0
    running = pid_running(pid)
    status = str(job.get("status") or "idle") if job else "idle"
    if status == "running" and not running:
        status = "finished_or_stopped"
    message = str(job.get("message") or "") if job else ""
    if not running and status == "finished_or_stopped":
        message = finished_job_message(job)
    return {
        "running": running,
        "pid": pid or None,
        "mode": job.get("mode") if job else None,
        "status": status,
        "message": message,
    }


def create_research_project(current_root: Path, task: str, name: str = "") -> dict[str, Any]:
    clean_task = task.strip()
    if not clean_task:
        raise ValueError("task must not be empty")
    workspace = workspace_for(current_root)
    workspace.mkdir(parents=True, exist_ok=True)
    project_dir = unique_project_dir(workspace, clean_task, name)
    research_dir = project_dir / ".research"
    researchctl.command_init(
        argparse.Namespace(research_dir=str(research_dir), task=clean_task, force=False)
    )
    return {
        "name": project_dir.name,
        "project_dir": str(project_dir),
        "research_dir": str(research_dir),
        "task": clean_task,
    }


def discover_projects(root: Path) -> list[dict[str, Any]]:
    current = normalize_research_root(root)
    workspace = workspace_for(current)
    candidates = [current]
    if workspace.exists():
        try:
            children = sorted(workspace.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            children = []
        for child in children:
            rd = child / ".research"
            try:
                available = rd.is_dir() and researchctl.state_path(rd).exists()
            except OSError:
                available = False
            if available:
                candidates.append(rd.resolve())
    seen: set[str] = set()
    projects: list[dict[str, Any]] = []
    for rd in candidates:
        key = str(rd.resolve())
        if key in seen:
            continue
        seen.add(key)
        try:
            state = researchctl.load_state(rd)
        except SystemExit:
            continue
        job = project_job_summary(rd)
        projects.append(
            {
                "name": rd.parent.name if rd.name == ".research" else rd.name,
                "research_dir": str(rd),
                "project_dir": str(rd.parent if rd.name == ".research" else rd),
                "task": state.get("task", ""),
                "phase": state.get("phase", ""),
                "running": job["running"],
                "job": job,
                "current": rd.resolve() == current.resolve(),
            }
        )
    return projects


def process_descendants(pid: int) -> list[int]:
    children: dict[int, list[int]] = {}
    for proc_dir in Path("/proc").iterdir() if Path("/proc").exists() else []:
        if not proc_dir.name.isdigit():
            continue
        try:
            stat = (proc_dir / "stat").read_text(encoding="utf-8", errors="ignore")
            parts = stat.split()
            if len(parts) > 4:
                ppid = int(parts[3])
                children.setdefault(ppid, []).append(int(proc_dir.name))
        except (OSError, ValueError):
            continue
    found: list[int] = []
    stack = list(children.get(pid, []))
    while stack:
        item = stack.pop()
        found.append(item)
        stack.extend(children.get(item, []))
    return found


def process_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").strip()


def process_session_paths(pid: int) -> list[Path]:
    fd_dir = Path(f"/proc/{pid}/fd")
    if not fd_dir.exists():
        return []
    paths: list[Path] = []
    try:
        fds = list(fd_dir.iterdir())
    except OSError:
        return []
    for fd in fds:
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if "/.codex/sessions/" not in target or not target.endswith(".jsonl"):
            continue
        path = Path(target)
        if path.exists() and path.is_file():
            paths.append(path)
    return paths


def active_codex_session_paths(root: Path) -> list[Path]:
    job = read_job(root)
    pid = int(job.get("pid") or 0) if job else 0
    if not pid_running(pid):
        return []
    paths: list[Path] = []
    for item in [pid, *process_descendants(pid)]:
        paths.extend(process_session_paths(item))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def latest_codex_session_paths(limit: int = 1) -> list[Path]:
    session_root = Path.home() / ".codex" / "sessions"
    if not session_root.exists():
        return []
    try:
        files = [path for path in session_root.rglob("*.jsonl") if path.is_file()]
    except OSError:
        return []
    files.sort(key=path_mtime, reverse=True)
    return files[:limit]


def path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def read_recent_lines(path: Path, max_bytes: int = 600_000) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            start = max(0, size - max_bytes)
            handle.seek(start)
            raw = handle.read()
    except OSError:
        return []
    if start > 0 and b"\n" in raw:
        raw = raw.split(b"\n", 1)[1]
    return raw.decode("utf-8", errors="ignore").splitlines()


def parse_event_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def rate_limit_payload(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    used = raw.get("used_percent")
    try:
        used_percent = float(used)
    except (TypeError, ValueError):
        used_percent = None
    remaining = None if used_percent is None else max(0.0, 100.0 - used_percent)
    resets_at = raw.get("resets_at")
    reset_iso = None
    reset_in_seconds = None
    if isinstance(resets_at, (int, float)):
        reset_time = datetime.fromtimestamp(float(resets_at)).astimezone()
        reset_iso = reset_time.isoformat()
        reset_in_seconds = max(0, int((reset_time - datetime.now().astimezone()).total_seconds()))
    return {
        "used_percent": used_percent,
        "remaining_percent": remaining,
        "window_minutes": raw.get("window_minutes"),
        "resets_at": reset_iso,
        "reset_in_seconds": reset_in_seconds,
    }


def token_usage_payload(raw: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    keys = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")
    payload: dict[str, int] = {}
    for key in keys:
        value = raw.get(key)
        if isinstance(value, int):
            payload[key] = value
    return payload


def codex_session_status(path: Path, source: str) -> dict[str, Any]:
    token_event: dict[str, Any] | None = None
    for line in reversed(read_recent_lines(path)):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload") if isinstance(event, dict) else None
        if isinstance(payload, dict) and payload.get("type") == "token_count":
            token_event = event
            break
    if token_event is None:
        return {
            "available": False,
            "source": source,
            "session_path": str(path),
            "message": "没有在 Codex session 中找到 token_count 事件",
        }
    payload = token_event.get("payload") or {}
    info = payload.get("info") if isinstance(payload, dict) else {}
    rate_limits = payload.get("rate_limits") if isinstance(payload, dict) else {}
    updated = parse_event_timestamp(str(token_event.get("timestamp") or ""))
    age = None if updated is None else max(0, int((datetime.now().astimezone() - updated).total_seconds()))
    return {
        "available": True,
        "source": source,
        "session_path": str(path),
        "updated_at": updated.isoformat() if updated else str(token_event.get("timestamp") or ""),
        "age_seconds": age,
        "plan_type": rate_limits.get("plan_type") if isinstance(rate_limits, dict) else None,
        "primary": rate_limit_payload(rate_limits.get("primary") if isinstance(rate_limits, dict) else None),
        "secondary": rate_limit_payload(rate_limits.get("secondary") if isinstance(rate_limits, dict) else None),
        "model_context_window": info.get("model_context_window") if isinstance(info, dict) else None,
        "total_token_usage": token_usage_payload(info.get("total_token_usage") if isinstance(info, dict) else None),
        "last_token_usage": token_usage_payload(info.get("last_token_usage") if isinstance(info, dict) else None),
    }


def codex_status(root: Path) -> dict[str, Any]:
    paths = active_codex_session_paths(root)
    source = "active"
    if not paths:
        paths = latest_codex_session_paths()
        source = "latest"
    if not paths:
        return {
            "available": False,
            "source": "none",
            "message": "没有找到 Codex session 文件",
        }
    paths.sort(key=path_mtime, reverse=True)
    return codex_session_status(paths[0], source)


def latest_activity(root: Path) -> dict[str, Any]:
    paths = [
        progress_feed_path(root),
        researchctl.log_path(root),
        root / "logs" / "paperfactory-run.out",
        root / "logs" / "codex-loop.out",
        root / "logs" / "review.out",
        researchctl.state_path(root),
    ]
    existing = [path for path in paths if path.exists()]
    if not existing:
        return {"path": None, "at": None, "age_seconds": None}
    latest = max(existing, key=lambda path: path.stat().st_mtime)
    mtime = datetime.fromtimestamp(latest.stat().st_mtime).astimezone()
    age = max(0, int((datetime.now().astimezone() - mtime).total_seconds()))
    return {"path": latest.relative_to(root).as_posix(), "at": mtime.isoformat(), "age_seconds": age}


def read_tail(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-limit:]


def job_path(root: Path) -> Path:
    return root / "logs" / JOB_FILE


def read_job(root: Path) -> dict[str, Any]:
    path = job_path(root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_job(root: Path, payload: dict[str, Any]) -> None:
    path = job_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fixed_cycle_job(job: dict[str, Any]) -> bool:
    command = job.get("command")
    return isinstance(command, list) and "--cycles" in [str(item) for item in command]


def finished_job_message(job: dict[str, Any]) -> str:
    if fixed_cycle_job(job):
        return "已按设定轮数结束；轮数留空可持续运行"
    if job.get("duration_minutes"):
        return "已到达设定运行时长或后台任务已结束"
    return "后台任务已结束"


def pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists():
        try:
            suffix = stat_path.read_text(encoding="utf-8", errors="ignore").rsplit(") ", 1)[1]
            if suffix.split()[0] == "Z":
                return False
        except (IndexError, OSError):
            pass
    return True


def stop_pid(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.killpg(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except OSError:
            return False


def intervention_path(root: Path) -> Path:
    return root / HUMAN_INTERVENTIONS


def progress_feed_path(root: Path) -> Path:
    return root / PROGRESS_FEED


def append_progress_event(
    root: Path,
    role: str,
    message: str,
    *,
    phase: str | None = None,
    status: str = "note",
    files: list[str] | None = None,
) -> None:
    text = message.strip()
    if not text:
        return
    path = progress_feed_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now().astimezone().isoformat(),
        "role": role,
        "phase": phase or "",
        "status": status,
        "message": text,
        "files": files or [],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_progress_feed(root: Path, limit: int = 80) -> list[dict[str, Any]]:
    path = progress_feed_path(root)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit * 2 :]:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        message = str(data.get("message") or "").strip()
        if not message:
            continue
        events.append(
            {
                "ts": str(data.get("ts") or ""),
                "role": str(data.get("role") or "agent"),
                "phase": str(data.get("phase") or ""),
                "status": str(data.get("status") or "note"),
                "message": message,
                "files": data.get("files") if isinstance(data.get("files"), list) else [],
            }
        )
    return events[-limit:]


def append_intervention(root: Path, message: str) -> None:
    text = message.strip()
    if not text:
        raise ValueError("Intervention message must not be empty")
    path = intervention_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {now()}\n\n{text}\n")
    researchctl.append_log(root, "Human intervention recorded; next generated prompt will include it")
    append_progress_event(root, "human", text, status="intervention")


def read_interventions(root: Path, limit_chars: int = 4000) -> str:
    path = intervention_path(root)
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text[-limit_chars:]


def memory_config_path(root: Path) -> Path:
    return root / MEMORY_CONFIG


def default_memory_config() -> dict[str, Any]:
    config = dict(MEMORY_PROFILES["balanced"]["config"])
    config["profile"] = "balanced"
    return config


def memory_profile_for(config: dict[str, Any]) -> str:
    for name, profile in MEMORY_PROFILES.items():
        if all(bool(config.get(key)) == bool(value) for key, value in profile["config"].items()):
            return name
    return "custom"


def read_memory_config(root: Path) -> dict[str, Any]:
    config = default_memory_config()
    path = memory_config_path(root)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}
        if isinstance(raw, dict):
            for key in ("summary", "logs", "human_interventions", "artifact_index"):
                if key in raw:
                    config[key] = bool(raw[key])
            if str(raw.get("profile") or "") in MEMORY_PROFILES:
                config["profile"] = str(raw["profile"])
    profile_name = memory_profile_for(config)
    if profile_name == "custom":
        config["profile"] = "custom"
        config["label"] = "自定义记忆"
        config["description"] = "你手动选择了记忆来源。"
    else:
        config["profile"] = profile_name
        config["label"] = str(MEMORY_PROFILES[profile_name]["label"])
        config["description"] = str(MEMORY_PROFILES[profile_name]["description"])
    config["profiles"] = {
        key: {"label": value["label"], "description": value["description"]}
        for key, value in MEMORY_PROFILES.items()
    }
    return config


def write_memory_config(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    current = read_memory_config(root)
    profile = str(config.get("profile") or "")
    if profile in MEMORY_PROFILES:
        for key, value in MEMORY_PROFILES[profile]["config"].items():
            current[key] = bool(value)
        current["profile"] = profile
    for key in ("summary", "logs", "human_interventions", "artifact_index"):
        if key in config:
            current[key] = bool(config[key])
    persist = {
        key: current[key]
        for key in ("profile", "summary", "logs", "human_interventions", "artifact_index")
        if key in current
    }
    memory_config_path(root).write_text(json.dumps(persist, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    researchctl.append_log(root, "Web UI memory config updated")
    return read_memory_config(root)


def stream_messages(root: Path, limit: int = 120) -> list[dict[str, str]]:
    events = read_progress_feed(root, limit)
    if not events:
        return []
    return [
        {
            "role": str(event.get("role") or "agent"),
            "text": str(event.get("message") or ""),
            "phase": str(event.get("phase") or ""),
            "status": str(event.get("status") or ""),
            "ts": str(event.get("ts") or ""),
            "files": event.get("files") if isinstance(event.get("files"), list) else [],
        }
        for event in events
    ]


def phase_by_key(root: Path, key: str) -> researchctl.Phase | None:
    for phase in researchctl.configured_phases(root):
        if phase.key == key:
            return phase
    return researchctl.PHASE_BY_KEY.get(key)


def phase_required(root: Path, phase: researchctl.Phase) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel in phase.required:
        path = root / rel
        present = path.exists() and path.stat().st_size > 0
        rows.append(
            {
                "path": rel,
                "present": present,
                "size": path.stat().st_size if path.exists() else 0,
                "url": f"/files/{urllib.parse.quote(rel)}" if path.exists() else None,
            }
        )
    return rows


def phase_health(root: Path, phase: researchctl.Phase, *, status: str, active: bool, completed: bool) -> dict[str, Any]:
    required = phase_required(root, phase)
    present = sum(1 for item in required if item["present"])
    total = len(required)
    report_status = researchctl.report_status(root, phase)
    missing = [str(item["path"]) for item in required if not item["present"]]
    if active and (report_status or "").lower() in researchctl.COMPLETE_STATUSES:
        label = "待复核"
        tone = "current"
    elif completed or (report_status or "").lower() in researchctl.COMPLETE_STATUSES:
        label = "已完成"
        tone = "complete"
    elif report_status and report_status.lower() in researchctl.NON_ADVANCING_STATUSES:
        label = "需要处理"
        tone = "stopped"
    elif missing and present:
        label = f"进行中 {present}/{total}"
        tone = "current" if active else "pending"
    elif missing:
        label = "未开始" if not active else "等待产物"
        tone = "pending" if not active else "waiting"
    elif report_status:
        label = f"报告：{report_status}"
        tone = "current" if active else "pending"
    else:
        label = "待总结"
        tone = "waiting"
    return {
        "status": status,
        "status_text": label,
        "status_tone": tone,
        "report_status": report_status or "missing",
        "missing": missing,
        "present_count": present,
        "required_count": total,
        "required": required,
    }


def route_history_payload(state: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    raw_routes: list[Any] = []
    if isinstance(state.get("phase_routes"), list):
        raw_routes.extend(state["phase_routes"])
    elif isinstance(state.get("phase_history"), list):
        raw_routes.extend(item.get("route") for item in state["phase_history"] if isinstance(item, dict) and item.get("route"))
    routes: list[dict[str, Any]] = []
    for item in raw_routes:
        if not isinstance(item, dict):
            continue
        routes.append(
            {
                "decision": str(item.get("decision") or ""),
                "from_phase": str(item.get("from_phase") or item.get("phase") or ""),
                "target_phase": str(item.get("target_phase") or ""),
                "resolved_next_phase": str(item.get("resolved_next_phase") or item.get("next_phase") or ""),
                "reason": str(item.get("reason") or ""),
                "confidence": item.get("confidence"),
                "decided_at": str(item.get("decided_at") or item.get("completed_at") or ""),
                "ignored": bool(item.get("ignored")),
                "ignore_reason": str(item.get("ignore_reason") or ""),
            }
        )
    return routes[-limit:]


def phase_payload(root: Path) -> dict[str, Any]:
    state = researchctl.load_state(root)
    phase = researchctl.current_phase(state, root)
    phase_key = "complete" if phase is None else phase.key
    done, total = progress(root, phase_key)
    history_entries = state.get("phase_history") if isinstance(state.get("phase_history"), list) else []
    completed_counts: dict[str, int] = {}
    for item in history_entries:
        if not isinstance(item, dict):
            continue
        key = str(item.get("phase") or "")
        if key:
            completed_counts[key] = completed_counts.get(key, 0) + 1
    history = set(completed_counts)
    routes = route_history_payload(state)
    last_route = routes[-1] if routes else None
    jump_count = sum(1 for item in routes if item.get("decision") not in ("", "advance"))
    phases = []
    workflow_rows = researchctl.workflow_config_for_ui(root)
    visible_index = 0
    for item in workflow_rows:
        key = str(item["key"])
        enabled = bool(item.get("enabled", True))
        if enabled:
            visible_index += 1
        if key == phase_key:
            status = "current"
        elif phase_key == "complete" or key in history:
            status = "complete"
        elif not enabled:
            status = "disabled"
        else:
            status = "pending"
        phase_obj = phase_by_key(root, key)
        health = (
            phase_health(root, phase_obj, status=status, active=key == phase_key, completed=key in history and key != phase_key)
            if phase_obj
            else {"status_text": "不可用", "status_tone": "stopped", "report_status": "missing", "missing": [], "present_count": 0, "required_count": 0}
        )
        phases.append(
            {
                "index": visible_index if enabled else "-",
                "key": key,
                "title": str(item.get("title") or ""),
                "objective": str(item.get("objective") or ""),
                "gate": str(item.get("gate") or ""),
                "enabled": enabled,
                "kind": str(item.get("kind") or "base"),
                "locked": bool(item.get("locked", False)),
                "insert_after": str(item.get("insert_after") or ""),
                "prompt": str(item.get("prompt") or ""),
                "status": status,
                "completed_count": completed_counts.get(key, 0),
                "active_visit_count": completed_counts.get(key, 0) + (1 if key == phase_key else 0),
                "revisited": completed_counts.get(key, 0) > 0 and key == phase_key,
                "page_url": f"/phase?key={urllib.parse.quote(key)}",
                **health,
            }
        )

    required: list[dict[str, Any]] = []
    missing: list[str] = []
    report_status = "complete"
    gate = "No active gate."
    title = "Complete"
    objective = "Workflow complete."
    if phase is not None:
        missing = researchctl.missing_required(root, phase)
        report_status = researchctl.report_status(root, phase) or "missing"
        gate = phase.gate
        title = phase.title
        objective = phase.objective
        required = phase_required(root, phase)
    health = (
        phase_health(root, phase, status="current", active=True, completed=False)
        if phase is not None
        else {"status_text": "全部完成", "status_tone": "complete", "present_count": 0, "required_count": 0}
    )

    return {
        "research_dir": str(root),
        "task": state.get("task", ""),
        "updated_at": state.get("updated_at"),
        "phase": {
            "key": phase_key,
            "title": title,
            "objective": objective,
            "gate": gate,
            "report_status": report_status,
            "display_status": health["status_text"],
            "status_tone": health["status_tone"],
            "present_count": health["present_count"],
            "required_count": health["required_count"],
            "missing": missing,
            "required": required,
            "page_url": f"/phase?key={urllib.parse.quote(phase_key)}",
            "completed_count": completed_counts.get(phase_key, 0),
            "active_visit_count": completed_counts.get(phase_key, 0) + (0 if phase_key == "complete" else 1),
            "revisited": completed_counts.get(phase_key, 0) > 0 and phase_key != "complete",
        },
        "progress": {"current": done, "total": total},
        "phases": phases,
        "route": last_route,
        "routes": routes,
        "route_summary": {
            "total": len(routes),
            "jumps": jump_count,
            "last": last_route,
        },
        "interventions": read_interventions(root),
    }


def progress(root: Path, phase_key: str) -> tuple[int, int]:
    phases = researchctl.configured_phases(root)
    total = len(phases)
    if phase_key == "complete":
        return total, total
    for index, phase in enumerate(phases, 1):
        if phase.key == phase_key:
            return index, total
    return 0, total


def write_next_prompt(root: Path) -> str:
    state = researchctl.load_state(root)
    prompt = researchctl.build_next_prompt(root, state)
    target = root / "next_prompt.md"
    target.write_text(prompt, encoding="utf-8")
    return prompt


def build_review_prompt(root: Path, venue: str, draft_path: str, mode: str = "deep-review") -> str:
    state = researchctl.load_state(root)
    draft = draft_path.strip() or "paper/paper_draft.md"
    output = ".research/reviews/top_conference_review.md"
    return f"""Use the manuscript-audit skill as a skeptical {venue or "top-tier ML/AI conference"} reviewer.

Research directory: {root}
Initial task: {state.get("task", "")}
Review mode: {mode}
Manuscript or draft path: {draft}
Write the review to: {output}

Instructions:
- Read .research/state.json, .research/task.md, .research/logs/research.log, and available paper/evidence artifacts before reviewing.
- Run the bundled manuscript checker when the draft is Markdown, LaTeX, or Typst, and apply paper-format-self-check for KLC-style final source/PDF hygiene.
- Review as a top-conference area reviewer: novelty, related work, method clarity, experimental protocol, baseline fairness, statistics, ablations, limitations, reproducibility, ethics, and claim support.
- Do not rewrite the paper. Produce a decision-oriented review and required revision roadmap.
- Do not invent missing experiments, citations, line numbers, metrics, or reviewer consensus.
- Mark each issue as blocker, major, moderate, or minor.
- Include concrete fixes and whether new experiments are required.
- Include format/PDF blockers such as smart quotes, malformed i.e./e.g., noisy BibTeX venue fields, arXiv citations for published work, breakable Figure/Table references, unreadable axes, table overflow, loose lists, missing appendix navigation, or excessive figure whitespace.
- If the paper is not ready, set the verdict to NEEDS_MORE_WORK or FAIL.

Output contract:

# Top Conference Review

## Verdict
PASS | FAIL | NEEDS_MORE_WORK

## Summary

## Strengths

## Submission Blockers

## Major Issues

## Moderate Issues

## Minor Issues

## Claim-to-Evidence Gaps

## Reproducibility And Ethics

## Required Revision Roadmap

## Re-Audit Checklist
"""


class JobManager:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None
        self.root: Path | None = None
        self.status: dict[str, Any] = {
            "running": False,
            "mode": None,
            "started_at": None,
            "stopped_at": None,
            "completed": 0,
            "last_rc": None,
            "dry_run": False,
            "message": "idle",
            "current_pid": None,
        }

    def snapshot(self) -> dict[str, Any]:
        if self.root is not None:
            job = read_job(self.root)
            pid = int(job.get("pid") or 0) if job else 0
            activity = latest_activity(self.root)
            with self.lock:
                proc = self.process
            if proc is not None and proc.pid == pid:
                running = proc.poll() is None
            else:
                running = pid_running(pid)
            if job:
                if not running and job.get("status") == "running":
                    job["status"] = "finished_or_stopped"
                    job["stopped_at"] = job.get("stopped_at") or datetime.now().astimezone().isoformat()
                    job["message"] = finished_job_message(job)
                    write_job(self.root, job)
                descendants = process_descendants(pid) if running and pid else []
                descendant_cmds = [process_cmdline(item) for item in descendants]
                codex_active = any("codex" in cmd and "exec" in cmd for cmd in descendant_cmds)
                if running and codex_active:
                    health = "active"
                    state_label = "Codex 正在执行"
                elif running:
                    health = "waiting"
                    state_label = "后台进程运行中，等待下一轮或等待 Codex 输出"
                elif job.get("status") == "stopped":
                    health = "stopped"
                    state_label = "已暂停"
                elif job.get("status") == "dry_run_complete":
                    health = "ready"
                    state_label = "演练完成"
                elif job.get("status") == "finished_or_stopped":
                    health = "ready"
                    state_label = "已结束"
                else:
                    health = "idle"
                    state_label = "未运行"
                job["running"] = running
                return {
                    "running": running,
                    "mode": job.get("mode"),
                    "started_at": job.get("started_at"),
                    "stopped_at": job.get("stopped_at"),
                    "completed": job.get("completed", 0),
                    "last_rc": job.get("last_rc"),
                    "dry_run": bool(job.get("dry_run")),
                    "message": job.get("message") or job.get("status") or "idle",
                    "current_pid": pid or None,
                    "detached": True,
                    "health": health,
                    "state_label": state_label,
                    "codex_active": codex_active,
                    "child_pids": descendants,
                    "last_activity": activity,
                }
        with self.lock:
            status = dict(self.status)
        status.setdefault("health", "idle")
        status.setdefault("state_label", "未运行")
        status.setdefault("codex_active", False)
        status.setdefault("last_activity", latest_activity(self.root) if self.root else {})
        return status

    def start_loop(
        self,
        root: Path,
        interval: int,
        cycles: int | None,
        dry_run: bool,
        codex_bin: str,
        duration_minutes: int | None = None,
    ) -> tuple[bool, str]:
        current = self.snapshot()
        if current.get("running"):
            return False, "后台任务正在运行。"
        if dry_run:
            write_next_prompt(root)
            researchctl.append_log(root, "Web UI dry-run cycle: prompt refreshed")
            write_job(
                root,
                {
                    "pid": None,
                    "mode": "loop",
                    "status": "dry_run_complete",
                    "started_at": datetime.now().astimezone().isoformat(),
                    "stopped_at": datetime.now().astimezone().isoformat(),
                    "completed": 1,
                    "last_rc": 0,
                    "dry_run": True,
                    "message": "干跑完成：已刷新下一步 prompt",
                },
            )
            return True, "干跑完成。"

        log_file = root / "logs" / "paperfactory-run.out"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "paperfactory.py"),
            "--research-dir",
            str(root),
            "run",
            "--interval",
            str(max(1, interval)),
            "--codex-bin",
            codex_bin,
        ]
        if duration_minutes is not None and duration_minutes > 0:
            until = datetime.now().astimezone() + timedelta(minutes=duration_minutes)
            cmd.extend(["--until", until.strftime("%Y-%m-%d %H:%M:%S")])
            run_message = f"按时长运行中，约 {duration_minutes} 分钟后结束"
        elif cycles is None:
            cmd.extend(["--until", "2099-01-01 00:00:00"])
            run_message = "持续运行中，关闭网页不影响进程"
        else:
            cmd.extend(["--cycles", str(max(1, int(cycles)))])
            run_message = f"固定 {max(1, int(cycles))} 轮运行中，跑完会自动结束"
        handle = log_file.open("a", encoding="utf-8")
        handle.write(f"\n[{now()}] detached paperfactory run start: {' '.join(cmd)}\n")
        handle.flush()
        proc = subprocess.Popen(
            cmd,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        handle.close()
        with self.lock:
            self.process = proc
        write_job(
            root,
            {
                "pid": proc.pid,
                "mode": "loop",
                "status": "running",
                "started_at": datetime.now().astimezone().isoformat(),
                "stopped_at": None,
                "completed": 0,
                "last_rc": None,
                "dry_run": False,
                "message": run_message,
                "duration_minutes": duration_minutes,
                "command": cmd,
                "log": "logs/paperfactory-run.out",
            },
        )
        researchctl.append_log(root, f"Web UI detached loop started: pid={proc.pid}")
        return True, f"后台任务已启动：PID {proc.pid}"

    def start_review(
        self,
        root: Path,
        venue: str,
        draft_path: str,
        mode: str,
        dry_run: bool,
        codex_bin: str,
    ) -> tuple[bool, str]:
        current = self.snapshot()
        if current.get("running"):
            return False, "后台任务正在运行。"
        prompt = build_review_prompt(root, venue, draft_path, mode)
        prompt_path = root / "reviews" / "top_conference_review_prompt.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        researchctl.append_log(root, f"Web UI review prompt generated: venue={venue or 'top conference'} mode={mode}")
        if dry_run:
            write_job(
                root,
                {
                    "pid": None,
                    "mode": "review",
                    "status": "dry_run_complete",
                    "started_at": datetime.now().astimezone().isoformat(),
                    "stopped_at": datetime.now().astimezone().isoformat(),
                    "completed": 1,
                    "last_rc": 0,
                    "dry_run": True,
                    "message": "干跑完成：已生成顶会审稿 prompt",
                },
            )
            return True, "审稿 prompt 已生成。"

        log_file = root / "logs" / "review.out"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handle = log_file.open("a", encoding="utf-8")
        handle.write(f"\n[{now()}] detached review start\n")
        handle.flush()
        proc = subprocess.Popen(
            [codex_bin, "exec", "--full-auto", "--skip-git-repo-check", prompt],
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        handle.close()
        with self.lock:
            self.process = proc
        write_job(
            root,
            {
                "pid": proc.pid,
                "mode": "review",
                "status": "running",
                "started_at": datetime.now().astimezone().isoformat(),
                "stopped_at": None,
                "completed": 0,
                "last_rc": None,
                "dry_run": False,
                "message": "后台审稿中，关闭网页不影响进程",
                "log": "logs/review.out",
            },
        )
        researchctl.append_log(root, f"Web UI detached review started: pid={proc.pid}")
        return True, f"后台审稿已启动：PID {proc.pid}"

    def stop(self) -> tuple[bool, str]:
        if self.root is not None:
            job = read_job(self.root)
            pid = int(job.get("pid") or 0) if job else 0
            stopped = stop_pid(pid)
            with self.lock:
                proc = self.process
            if proc is not None and proc.pid == pid:
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(pid, signal.SIGKILL)
                        proc.wait(timeout=3)
                    except OSError:
                        pass
            if job:
                job["status"] = "stopped"
                job["running"] = False
                job["stopped_at"] = datetime.now().astimezone().isoformat()
                job["message"] = "已请求暂停后台进程" if stopped else "没有发现可暂停的后台进程"
                write_job(self.root, job)
            researchctl.append_log(self.root, f"Web UI stop requested: pid={pid or 'none'} stopped={stopped}")
            return True, "已请求暂停后台任务。" if stopped else "没有正在运行的后台任务。"
        self.stop_event.set()
        with self.lock:
            proc = self.process
            self.status["message"] = "stopping"
        if proc and proc.poll() is None:
            proc.terminate()
            return True, "Stop requested; active Codex process was terminated."
        return True, "Stop requested."

    def _set(self, **values: Any) -> None:
        with self.lock:
            self.status.update(values)

    def _finish(self, message: str) -> None:
        self._set(
            running=False,
            stopped_at=datetime.now().astimezone().isoformat(),
            message=message,
            current_pid=None,
        )

    def _run_codex(self, root: Path, prompt: str, codex_bin: str, log_name: str) -> int:
        log_file = root / "logs" / log_name
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{now()}] codex job start\n")
            proc = subprocess.Popen(
                [codex_bin, "exec", "--full-auto", "--skip-git-repo-check", prompt],
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            with self.lock:
                self.process = proc
                self.status["current_pid"] = proc.pid
            while proc.poll() is None:
                if self.stop_event.is_set():
                    proc.terminate()
                    break
                time.sleep(0.5)
            rc = proc.wait()
            handle.write(f"[{now()}] codex job rc={rc}\n")
        with self.lock:
            self.process = None
            self.status["current_pid"] = None
        return int(rc)

    def _loop_worker(self, root: Path, interval: int, cycles: int | None, dry_run: bool, codex_bin: str) -> None:
        researchctl.append_log(root, f"Web UI loop start: interval={interval}s cycles={cycles or 'unbounded'} dry_run={dry_run}")
        completed = 0
        try:
            while not self.stop_event.is_set():
                if cycles is not None and completed >= cycles:
                    break
                prompt = write_next_prompt(root)
                if dry_run:
                    rc = 0
                    researchctl.append_log(root, "Web UI dry-run cycle: prompt refreshed")
                else:
                    rc = self._run_codex(root, prompt, codex_bin, "codex-loop.out")
                completed += 1
                self._set(completed=completed, last_rc=rc, message=f"completed {completed} cycle(s)")
                if rc != 0 or dry_run or (cycles is not None and completed >= cycles):
                    break
                self.stop_event.wait(interval)
        finally:
            reason = "stopped" if self.stop_event.is_set() else "finished"
            researchctl.append_log(root, f"Web UI loop {reason}: completed={completed}")
            self._finish(f"loop {reason}")

    def _review_worker(
        self,
        root: Path,
        venue: str,
        draft_path: str,
        mode: str,
        dry_run: bool,
        codex_bin: str,
    ) -> None:
        prompt = build_review_prompt(root, venue, draft_path, mode)
        prompt_path = root / "reviews" / "top_conference_review_prompt.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        researchctl.append_log(root, f"Web UI review prompt generated: venue={venue or 'top conference'} mode={mode}")
        try:
            if dry_run:
                rc = 0
                researchctl.append_log(root, "Web UI review dry-run: prompt written only")
            else:
                rc = self._run_codex(root, prompt, codex_bin, "review.out")
            self._set(completed=1, last_rc=rc, message=f"review rc={rc}")
        finally:
            reason = "stopped" if self.stop_event.is_set() else "finished"
            self._finish(f"review {reason}")


def list_artifacts(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    files = [path for path in root.rglob("*") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [file_entry(root, path) for path in files]


def list_figures(root: Path) -> list[dict[str, Any]]:
    figure_root = root / "figures"
    if not figure_root.exists():
        return []
    files = [path for path in figure_root.rglob("*") if path.is_file() and path.suffix.lower() in FIGURE_EXTENSIONS]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [file_entry(root, path) for path in files]


def artifact_preview(root: Path, rel: str) -> dict[str, Any]:
    path = root / safe_rel_path(rel)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(rel)
    entry = file_entry(root, path)
    if path.suffix.lower() in TEXT_EXTENSIONS or path.stat().st_size <= 64_000:
        try:
            entry["text"] = path.read_text(encoding="utf-8", errors="replace")[:80_000]
            entry["encoding"] = "text"
            return entry
        except OSError:
            pass
    entry["encoding"] = "base64"
    entry["data"] = base64.b64encode(path.read_bytes()[:80_000]).decode("ascii")
    return entry


def preview_html(root: Path, rel: str) -> bytes:
    path = root / safe_rel_path(rel)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(rel)
    entry = file_entry(root, path)
    safe_path = urllib.parse.quote(entry["path"])
    title = entry["path"]
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
        body = f'<img class="image" src="/files/{safe_path}" alt="{title}">'
    elif suffix == ".pdf":
        body = f'<iframe class="pdf" src="/files/{safe_path}"></iframe>'
    elif suffix in TEXT_EXTENSIONS or path.stat().st_size <= 500_000:
        text = path.read_text(encoding="utf-8", errors="replace")
        body = f"<pre>{html_escape(text)}</pre>"
    else:
        body = f'<p>该文件不适合直接预览。</p><a href="/files/{safe_path}">打开或下载</a>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(title)}</title>
  <style>
    body {{ margin: 0; background: #f5f7fb; color: #182235; font-family: Inter, system-ui, sans-serif; }}
    header {{ height: 56px; display: flex; align-items: center; justify-content: space-between; padding: 0 18px; background: #fff; border-bottom: 1px solid #d8dfeb; }}
    a {{ color: #2563eb; text-decoration: none; }}
    main {{ padding: 18px; }}
    pre {{ margin: 0; padding: 18px; min-height: calc(100vh - 100px); white-space: pre-wrap; overflow-wrap: anywhere; background: #fff; border: 1px solid #d8dfeb; border-radius: 10px; line-height: 1.55; }}
    .image {{ max-width: 100%; display: block; margin: 0 auto; background: #fff; border: 1px solid #d8dfeb; border-radius: 10px; }}
    .pdf {{ width: 100%; height: calc(100vh - 100px); border: 1px solid #d8dfeb; border-radius: 10px; background: #fff; }}
  </style>
</head>
<body>
  <header><strong>{html_escape(title)}</strong><a href="/files/{safe_path}">原文件</a></header>
  <main>{body}</main>
</body>
</html>
""".encode("utf-8")


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def simple_markdown_html(text: str) -> str:
    parts: list[str] = []
    in_code = False
    code_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            if in_code:
                parts.append(f"<pre>{html_escape(chr(10).join(code_lines))}</pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            parts.append("<div class=\"gap\"></div>")
        elif stripped.startswith("### "):
            parts.append(f"<h3>{html_escape(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            parts.append(f"<h2>{html_escape(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            parts.append(f"<h1>{html_escape(stripped[2:])}</h1>")
        elif stripped.startswith(("- ", "* ")):
            parts.append(f"<p class=\"bullet\">{html_escape(stripped[2:])}</p>")
        else:
            parts.append(f"<p>{html_escape(stripped)}</p>")
    if in_code:
        parts.append(f"<pre>{html_escape(chr(10).join(code_lines))}</pre>")
    return "\n".join(parts)


def phase_page_text(root: Path, key: str) -> tuple[str, str]:
    phase = phase_by_key(root, key)
    if phase is None:
        raise FileNotFoundError(key)
    page_path = root / "pages" / f"{key}.md"
    if page_path.exists():
        return phase.title, page_path.read_text(encoding="utf-8", errors="replace")
    health = phase_health(root, phase, status="current", active=False, completed=False)
    report = researchctl.report_for(root, phase)
    events = [
        event
        for event in read_progress_feed(root, 240)
        if str(event.get("phase") or "") == key
    ][-12:]
    lines = [
        f"# {phase.title}",
        "",
        f"阶段状态：{health['status_text']}",
        "",
        f"目标：{phase.objective}",
        "",
        f"门禁：{phase.gate}",
    ]
    if phase.kind == "custom" and phase.custom_prompt:
        lines.extend(["", "## 自定义 Prompt", phase.custom_prompt])
    lines.extend(["", "## 必需产物"])
    for item in health["required"]:
        mark = "已生成" if item["present"] else "未生成"
        lines.append(f"- {mark}: {item['path']}")
    if report:
        lines.extend(["", "## 阶段报告", "```json", json.dumps(report, indent=2, ensure_ascii=False), "```"])
    if events:
        lines.extend(["", "## 最近进展"])
        for event in events:
            msg = str(event.get("message") or "").strip()
            if msg:
                lines.append(f"- {msg}")
    if not page_path.exists():
        lines.extend(["", "## 提示", f"- Codex 下一轮应维护 pages/{key}.md，让这里变成自然语言阶段展示页。"])
    return phase.title, "\n".join(lines)


def phase_page_html(root: Path, key: str) -> bytes:
    title, text = phase_page_text(root, key)
    body = simple_markdown_html(text)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(title)}</title>
  <style>
    body {{ margin:0; background:#f6f8fb; color:#172033; font-family:Inter,system-ui,sans-serif; line-height:1.65; }}
    header {{ min-height:58px; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:0 22px; background:#fff; border-bottom:1px solid #d8e0ed; position:sticky; top:0; }}
    main {{ max-width:980px; margin:0 auto; padding:24px; }}
    article {{ background:#fff; border:1px solid #d8e0ed; border-radius:12px; padding:24px; box-shadow:0 16px 38px rgba(15,23,42,.07); }}
    h1 {{ margin:0 0 16px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:24px 0 10px; font-size:18px; letter-spacing:0; }}
    h3 {{ margin:18px 0 8px; font-size:15px; letter-spacing:0; }}
    p {{ margin:8px 0; }}
    .bullet {{ padding-left:18px; position:relative; }}
    .bullet::before {{ content:""; width:5px; height:5px; border-radius:99px; background:#2563eb; position:absolute; left:4px; top:.8em; }}
    .gap {{ height:8px; }}
    pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:#111827; color:#f9fafb; border-radius:10px; padding:14px; }}
    a {{ color:#2563eb; text-decoration:none; }}
  </style>
</head>
<body>
  <header><strong>{html_escape(title)}</strong><a href="/">返回控制台</a></header>
  <main><article>{body}</article></main>
</body>
</html>
""".encode("utf-8")


def index_html() -> bytes:
    return b"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex PaperFactory Control</title>
  <style>
    :root {
      --bg: #f6f7fb;
      --panel: #ffffff;
      --line: #d7deea;
      --text: #172033;
      --muted: #607089;
      --blue: #2563eb;
      --green: #0f8a5f;
      --amber: #b7791f;
      --red: #b42318;
      --ink: #111827;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }
    header {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }
    .wrap { width: min(1320px, calc(100vw - 32px)); margin: 0 auto; }
    header .wrap { padding: 18px 0; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    h1 { margin: 0; font-size: 24px; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 17px; letter-spacing: 0; }
    p { margin: 0; }
    main { padding: 16px 0 28px; }
    .grid { display: grid; grid-template-columns: 1.2fr .8fr; gap: 14px; }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
    section, .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    section { padding: 16px; margin-bottom: 14px; }
    .metric { padding: 12px; min-height: 88px; }
    .label { color: var(--muted); font-size: 12px; text-transform: uppercase; }
    .value { margin-top: 7px; font-size: 20px; font-weight: 700; overflow-wrap: anywhere; }
    .muted { color: var(--muted); }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    button, input, select, textarea {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
    }
    button {
      min-height: 34px;
      padding: 6px 10px;
      cursor: pointer;
      font-weight: 650;
    }
    button.primary { background: var(--blue); border-color: var(--blue); color: #fff; }
    button.danger { background: var(--red); border-color: var(--red); color: #fff; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    input, select { min-height: 34px; padding: 6px 8px; }
    textarea { width: 100%; min-height: 92px; padding: 8px; resize: vertical; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid transparent;
    }
    .ok, .complete { color: var(--green); background: #eaf7f1; border-color: #bce4d2; }
    .current { color: var(--blue); background: #eaf1ff; border-color: #b8cdfd; }
    .pending { color: var(--muted); background: #eef2f7; border-color: #d8dee8; }
    .missing, .error { color: var(--red); background: #fff0ee; border-color: #ffc9c2; }
    .warn { color: var(--amber); background: #fff8e7; border-color: #f4d28a; }
    .bar { height: 10px; background: #e8edf5; border-radius: 999px; overflow: hidden; margin-top: 10px; }
    .bar span { display: block; height: 100%; background: var(--blue); width: 0; }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    th, td { padding: 9px 7px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; overflow-wrap: anywhere; }
    th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
    pre {
      margin: 0;
      padding: 12px;
      background: var(--ink);
      color: #f9fafb;
      border-radius: 6px;
      overflow: auto;
      max-height: 360px;
      white-space: pre-wrap;
    }
    .logs { height: 360px; }
    .artifact-list { max-height: 320px; overflow: auto; border: 1px solid var(--line); border-radius: 6px; }
    .artifact-row {
      display: grid;
      grid-template-columns: 1fr 86px 74px;
      gap: 8px;
      padding: 8px;
      border-bottom: 1px solid var(--line);
      cursor: pointer;
      align-items: center;
    }
    .artifact-row:hover { background: #f2f6ff; }
    .figure-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
    .figure-item { border: 1px solid var(--line); border-radius: 8px; padding: 8px; background: #fff; }
    .figure-item img { max-width: 100%; height: 120px; object-fit: contain; display: block; margin: 0 auto 8px; }
    .tabs { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
    .tab.active { border-color: var(--blue); color: var(--blue); background: #eaf1ff; }
    .hidden { display: none; }
    @media (max-width: 980px) {
      .grid, .metrics { grid-template-columns: 1fr; }
      header .wrap { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <div>
        <h1>Codex PaperFactory Control</h1>
        <p class="muted" id="researchDir"></p>
      </div>
      <div class="row">
        <span id="runPill" class="pill pending">idle</span>
        <button id="refreshBtn">Refresh</button>
      </div>
    </div>
  </header>
  <main class="wrap">
    <div class="metrics">
      <div class="metric"><div class="label">Phase</div><div class="value" id="phaseKey">...</div></div>
      <div class="metric"><div class="label">Report</div><div class="value" id="reportStatus">...</div></div>
      <div class="metric"><div class="label">Progress</div><div class="value" id="progressText">...</div><div class="bar"><span id="progressBar"></span></div></div>
      <div class="metric"><div class="label">Missing</div><div class="value" id="missingCount">...</div></div>
    </div>
    <div class="grid">
      <div>
        <section>
          <h2>Task</h2>
          <textarea id="taskText"></textarea>
          <div class="row" style="margin-top:8px">
            <button class="primary" id="saveTaskBtn">Save Task</button>
            <button id="promptBtn">Generate Next Prompt</button>
          </div>
        </section>
        <section>
          <h2>Run Control</h2>
          <div class="row">
            <label>Interval <input id="intervalInput" type="number" min="1" value="1800" style="width:110px"></label>
            <label>Cycles <input id="cyclesInput" type="number" min="1" placeholder="blank = continuous" style="width:150px"></label>
            <label>Codex <input id="codexInput" value="codex" style="width:130px"></label>
            <label><input id="dryRunInput" type="checkbox"> Dry run</label>
            <button class="primary" id="startBtn">Start</button>
            <button class="danger" id="stopBtn">Pause</button>
          </div>
          <p class="muted" id="runMessage" style="margin-top:8px"></p>
        </section>
        <section>
          <h2>Current Gate</h2>
          <p><strong id="phaseTitle"></strong></p>
          <p class="muted" id="phaseObjective"></p>
          <p id="phaseGate" style="margin-top:8px"></p>
          <table style="margin-top:12px">
            <thead><tr><th>Status</th><th>Required Artifact</th><th>Size</th></tr></thead>
            <tbody id="artifactRequirements"></tbody>
          </table>
        </section>
        <section>
          <h2>Workflow</h2>
          <table>
            <thead><tr><th>#</th><th>Phase</th><th>State</th><th>Objective</th></tr></thead>
            <tbody id="phaseRows"></tbody>
          </table>
        </section>
      </div>
      <div>
        <section>
          <h2>Live Logs</h2>
          <pre class="logs" id="logs"></pre>
        </section>
        <section>
          <h2>Top Conference Review</h2>
          <div class="row">
            <label>Venue <input id="venueInput" value="NeurIPS/ICML/ICLR" style="width:170px"></label>
            <label>Draft <input id="draftInput" value="paper/paper_draft.md" style="width:170px"></label>
          </div>
          <div class="row" style="margin-top:8px">
            <select id="reviewMode">
              <option value="deep-review">deep-review</option>
              <option value="quick-audit">quick-audit</option>
              <option value="gate">gate</option>
            </select>
            <button id="reviewPromptBtn">Generate Review Prompt</button>
            <button class="primary" id="reviewRunBtn">Run Auto Review</button>
          </div>
          <textarea id="reviewPrompt" style="margin-top:8px; min-height:170px" readonly></textarea>
        </section>
      </div>
    </div>
    <section>
      <div class="tabs">
        <button class="tab active" data-tab="artifacts">Artifacts</button>
        <button class="tab" data-tab="figures">Figures</button>
        <button class="tab" data-tab="prompt">Prompt</button>
      </div>
      <div id="tab-artifacts">
        <div class="artifact-list" id="artifactList"></div>
        <h2 style="margin-top:14px">Preview</h2>
        <pre id="artifactPreview">Select an artifact.</pre>
      </div>
      <div id="tab-figures" class="hidden">
        <div class="figure-grid" id="figureGrid"></div>
      </div>
      <div id="tab-prompt" class="hidden">
        <textarea id="nextPrompt" readonly style="min-height:320px"></textarea>
      </div>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    let state = null;

    async function api(path, options = {}) {
      const res = await fetch(path, {
        headers: {'content-type': 'application/json'},
        ...options
      });
      if (!res.ok) {
        let text = await res.text();
        throw new Error(text || res.statusText);
      }
      return await res.json();
    }

    function pillClass(value) {
      if (value === 'complete' || value === 'OK' || value === true) return 'pill ok';
      if (value === 'current' || value === 'running') return 'pill current';
      if (value === 'missing' || value === false) return 'pill missing';
      return 'pill pending';
    }

    function renderStatus(payload) {
      state = payload;
      $('researchDir').textContent = payload.research_dir;
      $('phaseKey').textContent = payload.phase.key;
      $('reportStatus').textContent = payload.phase.report_status;
      $('progressText').textContent = `${payload.progress.current}/${payload.progress.total}`;
      $('progressBar').style.width = `${Math.round(payload.progress.current * 100 / payload.progress.total)}%`;
      $('missingCount').textContent = payload.phase.missing.length;
      $('taskText').value = payload.task || '';
      $('phaseTitle').textContent = payload.phase.title;
      $('phaseObjective').textContent = payload.phase.objective;
      $('phaseGate').textContent = payload.phase.gate;
      $('artifactRequirements').innerHTML = payload.phase.required.map(item => {
        const label = item.present ? 'OK' : 'MISSING';
        const link = item.url ? `<a href="${item.url}" target="_blank">${item.path}</a>` : item.path;
        return `<tr><td><span class="${pillClass(item.present)}">${label}</span></td><td>${link}</td><td>${item.size}</td></tr>`;
      }).join('') || '<tr><td colspan="3">No active requirements.</td></tr>';
      $('phaseRows').innerHTML = payload.phases.map(row =>
        `<tr><td>${row.index}</td><td><strong>${row.key}</strong><br><span class="muted">${row.title}</span></td><td><span class="pill ${row.status}">${row.status}</span></td><td>${row.objective}</td></tr>`
      ).join('');
      const job = payload.job || {};
      $('runPill').className = job.running ? 'pill current' : 'pill pending';
      $('runPill').textContent = job.running ? `${job.mode} running` : 'idle';
      $('runMessage').textContent = `${job.message || 'idle'}; completed=${job.completed || 0}; rc=${job.last_rc ?? 'none'}`;
      $('startBtn').disabled = !!job.running;
      $('reviewRunBtn').disabled = !!job.running;
      $('stopBtn').disabled = !job.running;
    }

    async function refreshStatus() {
      const payload = await api('/api/status');
      renderStatus(payload);
    }

    async function refreshLogs() {
      const payload = await api('/api/logs?limit=160');
      $('logs').textContent = payload.lines.join('\\n');
      $('logs').scrollTop = $('logs').scrollHeight;
    }

    async function refreshArtifacts() {
      const payload = await api('/api/artifacts');
      $('artifactList').innerHTML = payload.files.map(file =>
        `<div class="artifact-row" data-path="${file.path}"><span>${file.path}</span><span>${file.kind}</span><span>${file.size}</span></div>`
      ).join('') || '<div class="artifact-row">No artifacts yet.</div>';
      document.querySelectorAll('.artifact-row[data-path]').forEach(row => {
        row.addEventListener('click', () => previewArtifact(row.dataset.path));
      });
    }

    async function refreshFigures() {
      const payload = await api('/api/figures');
      $('figureGrid').innerHTML = payload.files.map(file => {
        const ext = file.path.split('.').pop().toLowerCase();
        const preview = ['svg', 'png', 'jpg', 'jpeg', 'webp'].includes(ext)
          ? `<img src="${file.url}" alt="${file.path}">`
          : `<div class="muted" style="height:120px; display:flex; align-items:center; justify-content:center">PDF figure</div>`;
        return `<div class="figure-item">${preview}<a href="${file.url}" target="_blank">${file.path}</a><p class="muted">${file.size} bytes</p></div>`;
      }).join('') || '<p class="muted">No figures under .research/figures yet.</p>';
    }

    async function previewArtifact(path) {
      const payload = await api('/api/artifact?path=' + encodeURIComponent(path));
      if (payload.encoding === 'text') {
        $('artifactPreview').textContent = payload.text;
      } else {
        $('artifactPreview').textContent = `Binary preview for ${payload.path}; open the file link instead.`;
      }
    }

    async function fullRefresh() {
      await Promise.all([refreshStatus(), refreshLogs(), refreshArtifacts(), refreshFigures()]);
    }

    $('refreshBtn').addEventListener('click', fullRefresh);
    $('saveTaskBtn').addEventListener('click', async () => {
      await api('/api/task', {method: 'POST', body: JSON.stringify({task: $('taskText').value})});
      await fullRefresh();
    });
    $('promptBtn').addEventListener('click', async () => {
      const payload = await api('/api/prompt', {method: 'POST', body: '{}'});
      $('nextPrompt').value = payload.prompt;
      document.querySelector('[data-tab="prompt"]').click();
      await refreshArtifacts();
    });
    $('startBtn').addEventListener('click', async () => {
      const cyclesRaw = $('cyclesInput').value.trim();
      await api('/api/run/start', {method: 'POST', body: JSON.stringify({
        interval: Number($('intervalInput').value || 1800),
        cycles: cyclesRaw ? Number(cyclesRaw) : null,
        dry_run: $('dryRunInput').checked,
        codex_bin: $('codexInput').value || 'codex'
      })});
      await fullRefresh();
    });
    $('stopBtn').addEventListener('click', async () => {
      await api('/api/run/stop', {method: 'POST', body: '{}'});
      await fullRefresh();
    });
    $('reviewPromptBtn').addEventListener('click', async () => {
      const payload = await api('/api/review/prompt', {method: 'POST', body: JSON.stringify({
        venue: $('venueInput').value,
        draft_path: $('draftInput').value,
        mode: $('reviewMode').value
      })});
      $('reviewPrompt').value = payload.prompt;
      await refreshArtifacts();
    });
    $('reviewRunBtn').addEventListener('click', async () => {
      const payload = await api('/api/review/start', {method: 'POST', body: JSON.stringify({
        venue: $('venueInput').value,
        draft_path: $('draftInput').value,
        mode: $('reviewMode').value,
        dry_run: $('dryRunInput').checked,
        codex_bin: $('codexInput').value || 'codex'
      })});
      $('reviewPrompt').value = payload.prompt;
      await fullRefresh();
    });
    document.querySelectorAll('.tab').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        ['artifacts', 'figures', 'prompt'].forEach(name => $('tab-' + name).classList.toggle('hidden', name !== btn.dataset.tab));
      });
    });
    fullRefresh();
    setInterval(() => { refreshStatus(); refreshLogs(); }, 2000);
  </script>
</body>
</html>
"""


def index_html_cn() -> bytes:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PaperFactory 智能体</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --line: #d9e0ec;
      --text: #162033;
      --muted: #627089;
      --blue: #2563eb;
      --green: #0f8a5f;
      --red: #b42318;
      --amber: #b7791f;
      --soft: #eef4ff;
      --ink: #101828;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
      line-height: 1.5;
    }
    header {
      height: 58px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 18px;
      gap: 12px;
    }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    h2 { margin: 0 0 10px; font-size: 15px; letter-spacing: 0; }
    p { margin: 0; }
    button, input, select, textarea {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
    }
    button {
      min-height: 34px;
      padding: 6px 10px;
      font-weight: 650;
      cursor: pointer;
    }
    button.primary { background: var(--blue); border-color: var(--blue); color: #fff; }
    button.danger { background: var(--red); border-color: var(--red); color: #fff; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    input, select { min-height: 34px; padding: 6px 8px; }
    textarea { width: 100%; min-height: 88px; padding: 8px; resize: vertical; }
    .muted { color: var(--muted); }
    .app {
      display: grid;
      grid-template-columns: 290px minmax(0, 1fr) 330px;
      gap: 12px;
      padding: 12px;
      height: calc(100vh - 58px);
      min-height: 640px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      overflow: hidden;
    }
    .stack { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .kv { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 6px; font-size: 13px; }
    .value { font-weight: 700; overflow-wrap: anywhere; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid transparent;
      white-space: nowrap;
    }
    .ok, .complete { color: var(--green); background: #eaf7f1; border-color: #bce4d2; }
    .current { color: var(--blue); background: #eaf1ff; border-color: #b8cdfd; }
    .pending { color: var(--muted); background: #eef2f7; border-color: #d8dee8; }
    .missing, .error { color: var(--red); background: #fff0ee; border-color: #ffc9c2; }
    .warn { color: var(--amber); background: #fff8e7; border-color: #f4d28a; }
    .bar { height: 10px; background: #e8edf5; border-radius: 999px; overflow: hidden; margin-top: 8px; }
    .bar span { display: block; height: 100%; background: var(--blue); width: 0; }
    .chat {
      display: flex;
      flex-direction: column;
      min-height: 0;
      height: 100%;
    }
    .stream {
      flex: 1;
      min-height: 0;
      overflow: auto;
      padding: 12px;
      background: #fbfcff;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .msg { display: flex; gap: 8px; margin-bottom: 10px; align-items: flex-start; }
    .avatar {
      flex: 0 0 42px;
      min-height: 24px;
      border-radius: 999px;
      background: var(--soft);
      color: var(--blue);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      font-weight: 800;
    }
    .bubble {
      max-width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 13px;
    }
    .msg.human { flex-direction: row-reverse; }
    .msg.human .avatar { background: #eaf7f1; color: var(--green); }
    .msg.human .bubble { background: #f1fbf6; }
    .composer { margin-top: 10px; }
    .control-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .list { max-height: 220px; overflow: auto; border: 1px solid var(--line); border-radius: 6px; }
    .item {
      padding: 8px;
      border-bottom: 1px solid var(--line);
      cursor: pointer;
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .item:hover { background: #f2f6ff; }
    pre {
      margin: 0;
      padding: 10px;
      background: var(--ink);
      color: #f9fafb;
      border-radius: 6px;
      overflow: auto;
      max-height: 260px;
      white-space: pre-wrap;
      font-size: 12px;
    }
    .tabs { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
    .tab.active { border-color: var(--blue); color: var(--blue); background: #eaf1ff; }
    .hidden { display: none; }
    @media (max-width: 1120px) {
      .app { grid-template-columns: 1fr; height: auto; }
      .chat { height: 720px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>PaperFactory 智能体</h1>
      <p class="muted" id="researchDir"></p>
    </div>
    <div class="row">
      <span id="runPill" class="pill pending">空闲</span>
      <button id="refreshBtn">刷新</button>
    </div>
  </header>
  <main class="app">
    <aside class="stack">
      <section>
        <h2>当前状态</h2>
        <div class="kv">
          <span class="muted">阶段</span><span class="value" id="phaseKey">...</span>
          <span class="muted">报告</span><span class="value" id="reportStatus">...</span>
          <span class="muted">进度</span><span class="value" id="progressText">...</span>
          <span class="muted">缺失</span><span class="value" id="missingCount">...</span>
        </div>
        <div class="bar"><span id="progressBar"></span></div>
      </section>
      <section>
        <h2>后台运行</h2>
        <p class="muted">网页关闭后仍继续跑；重新打开会读取 PID 和日志。</p>
        <div class="control-grid" style="margin-top:10px">
          <label>间隔秒<input id="intervalInput" type="number" min="1" value="1800"></label>
          <label>轮数<input id="cyclesInput" type="number" min="1" placeholder="留空=持续"></label>
        </div>
        <div class="row" style="margin-top:8px">
          <label><input id="dryRunInput" type="checkbox"> 只演练</label>
          <input id="codexInput" value="codex" style="width:110px">
        </div>
        <div class="row" style="margin-top:8px">
          <button class="primary" id="startBtn">启动</button>
          <button class="danger" id="stopBtn">暂停</button>
        </div>
        <p class="muted" id="runMessage" style="margin-top:8px"></p>
      </section>
      <section>
        <h2>任务</h2>
        <textarea id="taskText"></textarea>
        <div class="row" style="margin-top:8px">
          <button class="primary" id="saveTaskBtn">保存</button>
          <button id="promptBtn">生成提示</button>
        </div>
      </section>
      <section>
        <h2>门禁</h2>
        <p><strong id="phaseTitle"></strong></p>
        <p class="muted" id="phaseGate"></p>
      </section>
    </aside>
    <section class="chat">
      <h2>对话与执行流</h2>
      <p class="muted" style="margin-bottom:8px">这里显示 Codex CLI 的可见执行输出、工具日志和系统记录。</p>
      <div class="stream" id="stream"></div>
      <div class="composer">
        <textarea id="interventionText" placeholder="人工介入：写给 Codex 的新要求。当前正在跑的一轮不会即时接收；下一轮 prompt 会自动带上。"></textarea>
        <div class="row" style="margin-top:8px">
          <button class="primary" id="sendInterventionBtn">发送介入</button>
          <button id="rawLogBtn">查看原始日志</button>
        </div>
      </div>
    </section>
    <aside class="stack">
      <section>
        <h2>顶会审稿</h2>
        <div class="control-grid">
          <label>会议<input id="venueInput" value="NeurIPS/ICML/ICLR"></label>
          <label>稿件<input id="draftInput" value="paper/paper_draft.md"></label>
        </div>
        <select id="reviewMode" style="width:100%; margin-top:8px">
          <option value="deep-review">深度审稿</option>
          <option value="quick-audit">快速审查</option>
          <option value="gate">投稿门禁</option>
        </select>
        <div class="row" style="margin-top:8px">
          <button id="reviewPromptBtn">生成审稿提示</button>
          <button class="primary" id="reviewRunBtn">自动审稿</button>
        </div>
        <textarea id="reviewPrompt" style="margin-top:8px; min-height:130px" readonly></textarea>
      </section>
      <section>
        <div class="tabs">
          <button class="tab active" data-tab="artifacts">产物</button>
          <button class="tab" data-tab="figures">图表</button>
          <button class="tab" data-tab="prompt">提示</button>
        </div>
        <div id="tab-artifacts">
          <div class="list" id="artifactList"></div>
          <pre id="artifactPreview" style="margin-top:8px">选择产物预览</pre>
        </div>
        <div id="tab-figures" class="hidden">
          <div class="list" id="figureList"></div>
        </div>
        <div id="tab-prompt" class="hidden">
          <textarea id="nextPrompt" readonly style="min-height:260px"></textarea>
        </div>
      </section>
    </aside>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);

    async function api(path, options = {}) {
      const res = await fetch(path, {headers: {'content-type': 'application/json'}, ...options});
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }
    function cls(value) {
      if (value === true || value === 'complete') return 'pill ok';
      if (value === 'current' || value === 'running') return 'pill current';
      if (value === false || value === 'missing') return 'pill missing';
      return 'pill pending';
    }
    function renderStatus(payload) {
      $('researchDir').textContent = payload.research_dir;
      $('phaseKey').textContent = payload.phase.key;
      $('reportStatus').textContent = payload.phase.report_status;
      $('progressText').textContent = `${payload.progress.current}/${payload.progress.total}`;
      $('progressBar').style.width = `${Math.round(payload.progress.current * 100 / payload.progress.total)}%`;
      $('missingCount').textContent = payload.phase.missing.length;
      $('taskText').value = payload.task || '';
      $('phaseTitle').textContent = payload.phase.title;
      $('phaseGate').textContent = payload.phase.gate;
      const job = payload.job || {};
      $('runPill').className = job.running ? 'pill current' : 'pill pending';
      $('runPill').textContent = job.running ? `运行中 PID ${job.current_pid || ''}` : '空闲';
      $('runMessage').textContent = job.message || '空闲';
      $('startBtn').disabled = !!job.running;
      $('reviewRunBtn').disabled = !!job.running;
      $('stopBtn').disabled = !job.running;
    }
    function renderStream(messages) {
      $('stream').innerHTML = messages.map(m => {
        const human = m.role === '人工';
        return `<div class="msg ${human ? 'human' : ''}"><span class="avatar">${m.role}</span><div class="bubble">${escapeHtml(m.text)}</div></div>`;
      }).join('') || '<p class="muted">暂无输出</p>';
      $('stream').scrollTop = $('stream').scrollHeight;
    }
    function escapeHtml(text) {
      return String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    async function refreshStatus() {
      renderStatus(await api('/api/status'));
    }
    async function refreshStream() {
      const data = await api('/api/stream?limit=160');
      renderStream(data.messages);
    }
    async function refreshArtifacts() {
      const data = await api('/api/artifacts');
      $('artifactList').innerHTML = data.files.map(f => `<div class="item" data-path="${f.path}">${f.path}<br><span class="muted">${f.kind} · ${f.size} bytes</span></div>`).join('') || '<div class="item">暂无产物</div>';
      document.querySelectorAll('.item[data-path]').forEach(el => el.addEventListener('click', () => previewArtifact(el.dataset.path)));
    }
    async function refreshFigures() {
      const data = await api('/api/figures');
      $('figureList').innerHTML = data.files.map(f => `<div class="item"><a href="${f.url}" target="_blank">${f.path}</a><br><span class="muted">${f.size} bytes</span></div>`).join('') || '<div class="item">暂无图表</div>';
    }
    async function previewArtifact(path) {
      const data = await api('/api/artifact?path=' + encodeURIComponent(path));
      $('artifactPreview').textContent = data.encoding === 'text' ? data.text : `二进制文件：${data.path}`;
    }
    async function fullRefresh() {
      await Promise.all([refreshStatus(), refreshStream(), refreshArtifacts(), refreshFigures()]);
    }
    $('refreshBtn').addEventListener('click', fullRefresh);
    $('saveTaskBtn').addEventListener('click', async () => {
      await api('/api/task', {method: 'POST', body: JSON.stringify({task: $('taskText').value})});
      await fullRefresh();
    });
    $('promptBtn').addEventListener('click', async () => {
      const data = await api('/api/prompt', {method: 'POST', body: '{}'});
      $('nextPrompt').value = data.prompt;
      document.querySelector('[data-tab="prompt"]').click();
      await refreshArtifacts();
    });
    $('startBtn').addEventListener('click', async () => {
      const cyclesRaw = $('cyclesInput').value.trim();
      await api('/api/run/start', {method: 'POST', body: JSON.stringify({
        interval: Number($('intervalInput').value || 1800),
        cycles: cyclesRaw ? Number(cyclesRaw) : null,
        dry_run: $('dryRunInput').checked,
        codex_bin: $('codexInput').value || 'codex'
      })});
      await fullRefresh();
    });
    $('stopBtn').addEventListener('click', async () => {
      await api('/api/run/stop', {method: 'POST', body: '{}'});
      await fullRefresh();
    });
    $('sendInterventionBtn').addEventListener('click', async () => {
      const text = $('interventionText').value.trim();
      if (!text) return;
      const data = await api('/api/intervention', {method: 'POST', body: JSON.stringify({message: text})});
      $('nextPrompt').value = data.prompt;
      $('interventionText').value = '';
      await fullRefresh();
    });
    $('rawLogBtn').addEventListener('click', async () => {
      const data = await api('/api/logs?limit=220');
      $('artifactPreview').textContent = data.lines.join('\\n');
      document.querySelector('[data-tab="artifacts"]').click();
    });
    $('reviewPromptBtn').addEventListener('click', async () => {
      const data = await api('/api/review/prompt', {method: 'POST', body: JSON.stringify({
        venue: $('venueInput').value,
        draft_path: $('draftInput').value,
        mode: $('reviewMode').value
      })});
      $('reviewPrompt').value = data.prompt;
      await refreshArtifacts();
    });
    $('reviewRunBtn').addEventListener('click', async () => {
      const data = await api('/api/review/start', {method: 'POST', body: JSON.stringify({
        venue: $('venueInput').value,
        draft_path: $('draftInput').value,
        mode: $('reviewMode').value,
        dry_run: $('dryRunInput').checked,
        codex_bin: $('codexInput').value || 'codex'
      })});
      $('reviewPrompt').value = data.prompt;
      await fullRefresh();
    });
    document.querySelectorAll('.tab').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        ['artifacts', 'figures', 'prompt'].forEach(name => $('tab-' + name).classList.toggle('hidden', name !== btn.dataset.tab));
      });
    });
    fullRefresh();
    setInterval(() => { refreshStatus(); refreshStream(); }, 2000);
  </script>
</body>
</html>
""".encode("utf-8")


def index_html_cn_v2() -> bytes:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PaperFactory</title>
  <style>
    :root {
      --bg: #f6f7fb;
      --panel: #fff;
      --line: #d8dfeb;
      --text: #182235;
      --muted: #64748b;
      --blue: #2563eb;
      --green: #0f8a5f;
      --red: #b42318;
      --soft: #eef4ff;
      --ink: #111827;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 0 16px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }
    h1 { margin: 0; font-size: 19px; letter-spacing: 0; }
    h2 { margin: 0 0 10px; font-size: 14px; letter-spacing: 0; }
    p { margin: 0; }
    button, input, textarea {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
    }
    button { min-height: 32px; padding: 5px 10px; font-weight: 650; cursor: pointer; }
    button.primary { color: #fff; background: var(--blue); border-color: var(--blue); }
    button.danger { color: #fff; background: var(--red); border-color: var(--red); }
    button:disabled { opacity: .55; cursor: not-allowed; }
    input { min-height: 32px; padding: 5px 7px; width: 100%; }
    textarea { width: 100%; padding: 8px; resize: vertical; }
    .muted { color: var(--muted); }
    .app {
      height: calc(100vh - 56px);
      min-height: 680px;
      display: grid;
      grid-template-columns: 300px minmax(0, 1fr);
      gap: 12px;
      padding: 12px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      overflow: hidden;
    }
    .left { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
    .main { display: flex; flex-direction: column; min-height: 0; gap: 12px; }
    .row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid transparent;
      white-space: nowrap;
    }
    .ok, .complete { color: var(--green); background: #eaf7f1; border-color: #bce4d2; }
    .current { color: var(--blue); background: #eaf1ff; border-color: #b8cdfd; }
    .pending { color: var(--muted); background: #eef2f7; border-color: #d8dee8; }
    .missing, .error { color: var(--red); background: #fff0ee; border-color: #ffc9c2; }
    .flow {
      display: grid;
      grid-template-columns: repeat(10, minmax(86px, 1fr));
      gap: 6px;
      overflow-x: auto;
      padding-bottom: 2px;
    }
    .phase {
      min-height: 58px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 7px;
      background: #fff;
      font-size: 12px;
    }
    .phase.current { border-color: var(--blue); background: #edf4ff; color: var(--text); }
    .phase.complete { border-color: #bce4d2; background: #effaf5; color: var(--text); }
    .tree {
      flex: 1;
      min-height: 160px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcff;
    }
    .file {
      display: block;
      width: 100%;
      border: 0;
      border-bottom: 1px solid #edf1f7;
      border-radius: 0;
      text-align: left;
      background: transparent;
      font-size: 12px;
      font-weight: 500;
      overflow-wrap: anywhere;
    }
    .file:hover { background: #eef4ff; }
    .chat {
      flex: 1;
      min-height: 0;
      display: flex;
      flex-direction: column;
    }
    .feed {
      flex: 1;
      min-height: 0;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfcff;
    }
    .msg {
      display: grid;
      grid-template-columns: 54px minmax(0, 1fr);
      gap: 9px;
      margin-bottom: 12px;
      align-items: start;
    }
    .msg.human { grid-template-columns: minmax(0, 1fr) 54px; }
    .avatar {
      min-height: 26px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      background: var(--soft);
      color: var(--blue);
      font-size: 12px;
      font-weight: 800;
    }
    .human .avatar { background: #eaf7f1; color: var(--green); grid-column: 2; }
    .bubble {
      padding: 9px 11px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }
    .human .bubble { background: #f2fbf6; grid-column: 1; grid-row: 1; }
    .meta { margin-top: 6px; font-size: 12px; color: var(--muted); }
    .composer { margin-top: 10px; }
    .preview {
      max-height: 220px;
      overflow: auto;
      background: var(--ink);
      color: #f9fafb;
      padding: 10px;
      border-radius: 6px;
      white-space: pre-wrap;
      font-size: 12px;
    }
    label { font-size: 12px; color: var(--muted); }
    .memory label { display: flex; align-items: center; gap: 6px; color: var(--text); }
    .memory input { width: auto; min-height: auto; }
    @media (max-width: 980px) {
      .app { grid-template-columns: 1fr; height: auto; }
      .chat { height: 680px; }
      .flow { grid-template-columns: repeat(5, minmax(90px, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>PaperFactory</h1>
      <p class="muted" id="researchDir"></p>
    </div>
    <div class="row">
      <span id="runPill" class="pill pending">空闲</span>
      <button id="refreshBtn">刷新</button>
    </div>
  </header>
  <main class="app">
    <aside class="left">
      <section>
        <h2>运行</h2>
        <p><strong id="phaseKey">...</strong> <span class="muted" id="reportStatus"></span></p>
        <p class="muted" id="runMessage" style="margin-top:6px"></p>
        <div class="grid2" style="margin-top:10px">
          <label>间隔秒<input id="intervalInput" type="number" min="1" value="1800"></label>
          <label>轮数<input id="cyclesInput" type="number" min="1" placeholder="留空=持续"></label>
          <label>运行分钟<input id="durationInput" type="number" min="1" placeholder="可选"></label>
          <label>Codex<input id="codexInput" value="codex"></label>
        </div>
        <div class="row" style="margin-top:8px">
          <label><input id="dryRunInput" type="checkbox"> 只演练</label>
          <button class="primary" id="startBtn">启动</button>
          <button class="danger" id="stopBtn">暂停</button>
        </div>
      </section>
      <section class="memory">
        <h2>记忆</h2>
        <label><input type="checkbox" id="memSummary"> 摘要</label>
        <label><input type="checkbox" id="memLogs"> 日志</label>
        <label><input type="checkbox" id="memHuman"> 人工介入</label>
        <label><input type="checkbox" id="memArtifacts"> 当前产物</label>
        <button id="saveMemoryBtn" style="margin-top:8px">保存记忆</button>
      </section>
      <section style="flex:1; display:flex; flex-direction:column; min-height:0">
        <h2>文件树</h2>
        <div class="tree" id="fileTree"></div>
      </section>
      <section>
        <h2>预览</h2>
        <div class="preview" id="filePreview">选择文件</div>
      </section>
    </aside>
    <div class="main">
      <section>
        <h2>流程</h2>
        <div class="flow" id="phaseFlow"></div>
      </section>
      <section class="chat">
        <h2>Codex 进展</h2>
        <p class="muted" style="margin-bottom:8px">这里展示 Codex 自己写给你的自然语言进展，不展示原始日志。</p>
        <div class="feed" id="feed"></div>
        <div class="composer">
          <textarea id="interventionText" placeholder="中途介入：写下你的新要求。下一轮会自动带给 Codex；需要立刻改变方向时先暂停再启动。"></textarea>
          <div class="row" style="margin-top:8px">
            <button class="primary" id="sendInterventionBtn">发送介入</button>
            <button id="promptBtn">生成下一轮提示</button>
          </div>
        </div>
      </section>
    </div>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const roleName = {agent: 'Codex', human: '你', system: '系统'};
    let workflowDirty = false;
    let draggedWorkflowKey = null;

    async function api(path, options = {}) {
      const res = await fetch(path, {headers: {'content-type': 'application/json'}, ...options});
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }
    function esc(text) {
      return String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function formatMessageTime(ts) {
      if (!ts) return '';
      const date = new Date(ts);
      if (Number.isNaN(date.getTime())) return String(ts);
      return date.toLocaleString('zh-CN', {
        hour12: false,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
    }
    function renderStatus(data) {
      $('researchDir').textContent = data.research_dir;
      $('phaseKey').textContent = data.phase.key;
      $('reportStatus').textContent = data.phase.report_status;
      const job = data.job || {};
      $('runPill').className = job.running ? 'pill current' : 'pill pending';
      $('runPill').textContent = job.running ? `运行中 ${job.current_pid || ''}` : '空闲';
      $('runMessage').textContent = job.message || '等待启动';
      $('startBtn').disabled = !!job.running;
      $('stopBtn').disabled = !job.running;
      $('phaseFlow').innerHTML = data.phases.map(p =>
        `<div class="phase ${p.status}"><strong>${p.index}. ${p.key}</strong><br><span>${p.title}</span></div>`
      ).join('');
    }
    function renderFeed(data) {
      const feed = $('feed');
      const bottomOffset = feed.scrollHeight - feed.scrollTop;
      const shouldFollow = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
      $('feed').innerHTML = data.messages.map(m => {
        const human = m.role === 'human';
        const files = Array.isArray(m.files) && m.files.length ? `<div class="meta">产物：${m.files.map(esc).join(', ')}</div>` : '';
        const time = formatMessageTime(m.ts);
        const meta = [m.phase, m.status, time ? `时间 ${time}` : ''].filter(Boolean).join(' · ');
        return `<div class="msg ${human ? 'human' : ''}">
          <span class="avatar">${roleName[m.role] || m.role}</span>
          <div class="bubble">${esc(m.text)}${meta ? `<div class="meta">${esc(meta)}</div>` : ''}${files}</div>
        </div>`;
      }).join('');
      if (shouldFollow) feed.scrollTop = feed.scrollHeight;
      else feed.scrollTop = Math.max(0, feed.scrollHeight - bottomOffset);
    }
    async function refreshStatus() { renderStatus(await api('/api/status')); }
    async function refreshFeed() { renderFeed(await api('/api/stream?limit=80')); }
    async function refreshTree() {
      const data = await api('/api/tree');
      $('fileTree').innerHTML = data.files.map(f =>
        `<button class="file" data-path="${esc(f.path)}" style="padding-left:${8 + f.depth * 14}px">${esc(f.path)}</button>`
      ).join('') || '<p class="muted" style="padding:8px">暂无文件</p>';
      document.querySelectorAll('.file[data-path]').forEach(el => el.addEventListener('click', () => previewFile(el.dataset.path)));
    }
    async function previewFile(path) {
      const data = await api('/api/artifact?path=' + encodeURIComponent(path));
      $('filePreview').textContent = data.encoding === 'text' ? data.text : `二进制文件：${data.path}`;
    }
    async function refreshMemory() {
      const mem = await api('/api/memory');
      $('memSummary').checked = !!mem.summary;
      $('memLogs').checked = !!mem.logs;
      $('memHuman').checked = !!mem.human_interventions;
      $('memArtifacts').checked = !!mem.artifact_index;
    }
    async function refreshAll() {
      await Promise.all([refreshStatus(), refreshFeed(), refreshTree(), refreshMemory()]);
    }
    $('refreshBtn').addEventListener('click', refreshAll);
    $('startBtn').addEventListener('click', async () => {
      const cycles = $('cyclesInput').value.trim();
      const duration = $('durationInput').value.trim();
      await api('/api/run/start', {method: 'POST', body: JSON.stringify({
        interval: Number($('intervalInput').value || 1800),
        cycles: cycles ? Number(cycles) : null,
        duration_minutes: duration ? Number(duration) : null,
        dry_run: $('dryRunInput').checked,
        codex_bin: $('codexInput').value || 'codex'
      })});
      await refreshAll();
    });
    $('stopBtn').addEventListener('click', async () => {
      await api('/api/run/stop', {method: 'POST', body: '{}'});
      await refreshAll();
    });
    $('sendInterventionBtn').addEventListener('click', async () => {
      const message = $('interventionText').value.trim();
      if (!message) return;
      await api('/api/intervention', {method: 'POST', body: JSON.stringify({message})});
      $('interventionText').value = '';
      await refreshAll();
    });
    $('promptBtn').addEventListener('click', async () => {
      await api('/api/prompt', {method: 'POST', body: '{}'});
      await refreshTree();
      await refreshFeed();
    });
    $('saveMemoryBtn').addEventListener('click', async () => {
      await api('/api/memory', {method: 'POST', body: JSON.stringify({
        summary: $('memSummary').checked,
        logs: $('memLogs').checked,
        human_interventions: $('memHuman').checked,
        artifact_index: $('memArtifacts').checked
      })});
      await refreshMemory();
    });
    refreshAll();
    setInterval(() => { refreshStatus(); refreshFeed(); refreshTree(); }, 2500);
  </script>
</body>
</html>
""".encode("utf-8")


def index_html_cn_v3() -> bytes:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PaperFactory</title>
  <style>
    :root {
      --bg: #eef2f7;
      --panel: rgba(255,255,255,.92);
      --solid: #fff;
      --line: #d8e0ed;
      --text: #152033;
      --muted: #64748b;
      --blue: #2563eb;
      --green: #0f8a5f;
      --red: #b42318;
      --amber: #a16207;
      --soft-blue: #eaf1ff;
      --shadow: 0 18px 45px rgba(15,23,42,.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: linear-gradient(180deg, #f9fafb 0%, #eef2f7 58%, #e8eef5 100%);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    header {
      height: 64px;
      padding: 0 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(216,224,237,.75);
      background: rgba(255,255,255,.72);
      backdrop-filter: blur(14px);
      position: sticky;
      top: 0;
      z-index: 4;
    }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 15px; letter-spacing: 0; }
    p { margin: 0; }
    button, input, textarea, select {
      font: inherit;
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    button { min-height: 34px; padding: 6px 11px; font-weight: 700; cursor: pointer; }
    button.primary { background: var(--blue); border-color: var(--blue); color: #fff; }
    button.danger { background: var(--red); border-color: var(--red); color: #fff; }
    button.ghost { background: transparent; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    input, select { min-height: 34px; padding: 6px 8px; width: 100%; }
    input[type="checkbox"] { width: auto; min-height: auto; padding: 0; }
    textarea { width: 100%; min-height: 84px; padding: 9px; resize: vertical; }
    a { color: var(--blue); text-decoration: none; }
    .muted { color: var(--muted); }
    .app {
      display: grid;
      grid-template-columns: 300px minmax(0, 1fr);
      gap: 16px;
      padding: 16px;
      max-width: 1560px;
      margin: 0 auto;
    }
    .side, .main { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
    section, .hero {
      background: var(--panel);
      border: 1px solid rgba(216,224,237,.86);
      border-radius: 14px;
      box-shadow: var(--shadow);
    }
    section { padding: 14px; }
    .hero { padding: 18px; }
    .topline { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
    .statusTitle { font-size: 28px; font-weight: 820; letter-spacing: 0; margin-top: 6px; }
    .statusSub { color: var(--muted); margin-top: 6px; }
    .dot {
      width: 12px;
      height: 12px;
      border-radius: 99px;
      background: var(--muted);
      box-shadow: 0 0 0 5px rgba(100,116,139,.13);
      margin-top: 6px;
      flex: 0 0 auto;
    }
    .dot.active { background: var(--green); box-shadow: 0 0 0 5px rgba(15,138,95,.14); }
    .dot.waiting { background: var(--amber); box-shadow: 0 0 0 5px rgba(161,98,7,.14); }
    .dot.stopped, .dot.error { background: var(--red); box-shadow: 0 0 0 5px rgba(180,35,24,.13); }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 10px; margin-top: 16px; }
    .metric { padding: 11px; border: 1px solid var(--line); border-radius: 10px; background: rgba(255,255,255,.72); min-height: 72px; }
    .label { font-size: 12px; color: var(--muted); }
    .value { font-size: 17px; font-weight: 760; margin-top: 5px; overflow-wrap: anywhere; }
    .flow { display: grid; grid-template-columns: repeat(10, minmax(98px,1fr)); gap: 7px; overflow-x: auto; }
    .phase { border: 1px solid var(--line); border-radius: 10px; padding: 8px; background: #fff; font-size: 12px; min-height: 74px; text-align:left; font-weight:600; }
    .phase.current { border-color: var(--blue); background: var(--soft-blue); }
    .phase.complete { border-color: #bce4d2; background: #effaf5; }
    .phase.custom { border-color: #c4b5fd; background: #f5f3ff; }
    .phase.revisited { box-shadow: inset 0 0 0 2px rgba(161,98,7,.18); }
    .phase.disabled { opacity:.48; background:#f8fafc; }
    .phase .phaseMeta { display:block; margin-top:5px; color:var(--muted); font-weight:600; }
    .workflowEditor { display:grid; gap:8px; margin-top:12px; }
    .workflowRow { display:grid; gap:8px; padding:10px; border:1px solid var(--line); border-radius:10px; background:#fff; }
    .workflowRowHeader { display:grid; grid-template-columns: 72px minmax(140px,1fr) 150px 74px; gap:8px; align-items:center; }
    .workflowRow input[type="text"] { min-height:32px; }
    .workflowRow textarea { min-height:76px; }
    .lockNote { border:1px dashed var(--line); border-radius:10px; padding:10px; color:var(--muted); background:#fbfdff; font-size:13px; }
    .tiny { font-size:12px; color:var(--muted); }
    .row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .row > input { flex: 1 1 180px; width: auto; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
    .projectSelect { margin-top: 8px; }
    .newProjectBox { display:grid; gap:8px; margin-top:10px; padding-top:10px; border-top:1px solid var(--line); }
    .newProjectBox textarea { min-height:74px; }
    .tree { max-height: 420px; overflow: auto; border: 1px solid var(--line); border-radius: 10px; background: #fbfdff; padding:4px 0; }
    .treeFolder { margin:0; }
    .treeFolder summary { min-height:30px; display:flex; align-items:center; justify-content:space-between; gap:8px; padding:5px 8px; color:var(--text); font-size:12px; font-weight:760; border-bottom:1px solid #edf2f7; cursor:pointer; }
    .treeFolder summary:hover { background:var(--soft-blue); }
    .treeCount { color:var(--muted); font-size:11px; font-weight:700; }
    .file { width: 100%; min-height:30px; display: flex; align-items:center; justify-content:space-between; gap:8px; border: 0; border-bottom: 1px solid #edf2f7; border-radius: 0; background: transparent; text-align: left; font-size: 12px; font-weight: 550; overflow-wrap: anywhere; }
    .file:hover { background: var(--soft-blue); }
    .fileName { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .fileKind { color:var(--muted); font-size:11px; flex:0 0 auto; }
    .feed { min-height: 430px; max-height: calc(100vh - 445px); overflow: auto; border: 1px solid var(--line); border-radius: 12px; background: #fbfdff; padding: 14px; }
    .empty { min-height: 170px; display: grid; place-items: center; color: var(--muted); text-align: center; padding: 24px; }
    .msg { display: grid; grid-template-columns: 56px minmax(0,1fr); gap: 10px; align-items: start; margin-bottom: 13px; }
    .msg.human { grid-template-columns: minmax(0,1fr) 56px; }
    .avatar { min-height: 28px; border-radius: 99px; display: inline-flex; align-items: center; justify-content: center; background: var(--soft-blue); color: var(--blue); font-size: 12px; font-weight: 850; }
    .human .avatar { grid-column: 2; background: #eaf7f1; color: var(--green); }
    .bubble { padding: 10px 12px; border: 1px solid var(--line); border-radius: 12px; background: #fff; white-space: pre-wrap; overflow-wrap: anywhere; }
    .human .bubble { grid-column: 1; grid-row: 1; background: #f2fbf6; }
    .meta { margin-top: 7px; color: var(--muted); font-size: 12px; }
    .composer { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 9px; margin-top: 10px; align-items: end; }
    .memory label { display: flex; gap: 7px; align-items: center; color: var(--text); font-size: 13px; }
    .memory input { width: auto; min-height: auto; }
    details { margin-top:10px; }
    summary { cursor:pointer; color:var(--muted); font-size:13px; }
    .foldSection { padding:0; overflow:hidden; }
    .foldSection details { margin:0; }
    .foldHead { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:14px; color:var(--text); font-size:15px; font-weight:800; list-style:none; }
    .foldHead::-webkit-details-marker { display:none; }
    .foldHead::after { content:"收起"; color:var(--muted); font-size:12px; font-weight:700; }
    details:not([open]) > .foldHead::after { content:"展开"; }
    .foldBody { padding:0 14px 14px; }
    .routePanel { border-color:#f3c36b; background:linear-gradient(180deg,#fffaf0 0%,rgba(255,255,255,.92) 100%); }
    .routePanel.ignored { border-color:#fca5a5; background:linear-gradient(180deg,#fff1f2 0%,rgba(255,255,255,.92) 100%); }
    .routeHeadline { font-size:17px; font-weight:840; margin-bottom:5px; }
    .routeList { display:grid; gap:8px; margin-top:12px; }
    .routeItem { display:grid; gap:4px; padding:9px; border:1px solid var(--line); border-radius:10px; background:#fff; }
    .routeItem strong { font-size:13px; }
    .routeMeta { color:var(--muted); font-size:12px; }
    .quota { display: grid; gap: 9px; }
    .quotaHead { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .quotaValue { font-weight: 820; }
    .quotaBar { height: 7px; border-radius: 999px; background: #e5eaf2; overflow: hidden; }
    .quotaBar span { display: block; height: 100%; width: 0%; border-radius: inherit; background: var(--green); transition: width .2s ease; }
    .quotaBar.low span { background: var(--red); }
    .quotaBar.mid span { background: var(--amber); }
    .pill { display: inline-flex; align-items: center; min-height: 24px; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 760; background: #eef2f7; color: var(--muted); }
    .pill.active { color: var(--green); background: #eaf7f1; }
    .pill.waiting { color: var(--amber); background: #fff8e7; }
    .pill.stopped { color: var(--red); background: #fff0ee; }
    .notice { margin: 12px auto 0; max-width: 1560px; padding: 9px 14px; border: 1px solid #fed7aa; border-radius: 10px; background: #fff7ed; color: #9a3412; }
    @media (max-width: 1050px) {
      .app { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: 1fr 1fr; }
      .flow { grid-template-columns: repeat(5, minmax(92px,1fr)); }
      .feed { max-height: none; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>PaperFactory</h1>
      <p class="muted" id="researchDir"></p>
    </div>
    <div class="row">
      <span id="headerState" class="pill">状态读取中</span>
      <button class="ghost" id="refreshBtn">刷新</button>
    </div>
  </header>
  <div id="errorBar" class="notice" hidden></div>
  <main class="app">
    <aside class="side">
      <section>
        <h2>研究任务</h2>
        <select id="projectSelect" class="projectSelect"></select>
        <div class="row" style="margin-top:8px">
          <input id="projectPathInput" placeholder="输入 .research 或项目目录路径">
          <button id="switchPathBtn">切换</button>
        </div>
        <div class="newProjectBox">
          <textarea id="newProjectTask" placeholder="输入新研究方向"></textarea>
          <input id="newProjectName" placeholder="方向简称（可选）">
          <button class="primary" id="newProjectBtn">新建并切换</button>
          <p class="tiny">自动生成独立文件夹，旧研究继续后台运行。</p>
        </div>
      </section>
      <section>
        <h2>运行控制</h2>
        <div class="grid2">
          <label>间隔秒<input id="intervalInput" type="number" min="1" value="1800"></label>
          <label>轮数<input id="cyclesInput" type="number" min="1" placeholder="留空=持续"></label>
          <label>运行分钟<input id="durationInput" type="number" min="1" placeholder="可选"></label>
          <label>Codex<input id="codexInput" value="codex"></label>
        </div>
        <div class="row" style="margin-top:10px">
          <label><input id="dryRunInput" type="checkbox"> 只演练</label>
          <button class="primary" id="startBtn">启动</button>
          <button class="danger" id="stopBtn">暂停</button>
        </div>
        <p class="tiny" style="margin-top:8px">默认持续运行；填写轮数时，跑完指定轮数会自动结束。</p>
      </section>
      <section class="memory">
        <h2>记忆</h2>
        <select id="memoryProfile">
          <option value="balanced">标准记忆</option>
          <option value="focused">轻量记忆</option>
          <option value="deep">深度记忆</option>
          <option value="clean">干净启动</option>
          <option value="custom">自定义</option>
        </select>
        <p class="tiny" id="memoryProfileText" style="margin-top:7px"></p>
        <details>
          <summary>高级来源</summary>
          <label><input type="checkbox" id="memSummary"> 研究摘要</label>
          <label><input type="checkbox" id="memLogs"> 运行记录</label>
          <label><input type="checkbox" id="memHuman"> 人工介入</label>
          <label><input type="checkbox" id="memArtifacts"> 当前阶段产物</label>
        </details>
        <button id="saveMemoryBtn" style="margin-top:10px">保存</button>
      </section>
      <section>
        <h2>Codex 状态</h2>
        <div class="quota">
          <div>
            <div class="quotaHead"><span class="label" id="codexPrimaryLabel">短周期余量</span><span class="quotaValue" id="codexPrimaryValue">-</span></div>
            <div class="quotaBar" id="codexPrimaryBarWrap"><span id="codexPrimaryBar"></span></div>
          </div>
          <div>
            <div class="quotaHead"><span class="label" id="codexSecondaryLabel">长周期余量</span><span class="quotaValue" id="codexSecondaryValue">-</span></div>
            <div class="quotaBar" id="codexSecondaryBarWrap"><span id="codexSecondaryBar"></span></div>
          </div>
          <div class="grid2">
            <div><div class="label">计划</div><div class="value" id="codexPlan">-</div></div>
            <div><div class="label">上下文</div><div class="value" id="codexContext">-</div></div>
          </div>
          <p class="muted" id="codexStatusMeta">等待读取 Codex session</p>
        </div>
      </section>
      <section class="foldSection">
        <details id="fileTreeDetails" open>
          <summary class="foldHead"><span>文件树</span><span class="tiny" id="fileTreeCount">-</span></summary>
          <div class="foldBody">
            <div class="tree" id="fileTree"></div>
          </div>
        </details>
      </section>
    </aside>
    <div class="main">
      <div class="hero">
        <div class="topline">
          <div class="row" style="align-items:flex-start">
            <span id="statusDot" class="dot"></span>
            <div>
              <div class="label">运行状态</div>
              <div class="statusTitle" id="statusTitle">正在读取</div>
              <p class="statusSub" id="statusSub">请稍候</p>
            </div>
          </div>
          <span id="jobMode" class="pill">-</span>
        </div>
        <div class="metrics">
          <div class="metric"><div class="label">当前阶段</div><div class="value" id="phaseKey">-</div></div>
          <div class="metric"><div class="label">阶段报告</div><div class="value" id="reportStatus">-</div></div>
          <div class="metric"><div class="label">PID</div><div class="value" id="pidValue">-</div></div>
          <div class="metric"><div class="label">最后活动</div><div class="value" id="lastActivity">-</div></div>
        </div>
      </div>
      <section class="routePanel" id="routePanel" hidden>
        <div class="row" style="justify-content:space-between">
          <h2>阶段路由</h2>
          <span class="pill waiting" id="routeCount">0 次</span>
        </div>
        <div class="routeHeadline" id="routeHeadline">暂无路由决策</div>
        <p class="muted" id="routeSub"></p>
        <details id="routeHistoryDetails">
          <summary>查看路由历史</summary>
          <div class="routeList" id="routeList"></div>
        </details>
      </section>
      <section>
        <div class="row" style="justify-content:space-between">
          <h2>流程</h2>
          <div class="row">
            <button id="addCustomPhaseBtn">添加阶段</button>
            <button id="resetWorkflowBtn">清空自定义</button>
            <button class="primary" id="saveWorkflowBtn">保存流程</button>
          </div>
        </div>
        <p class="muted" style="margin-bottom:10px">主干阶段固定不可改；你可以在主干之间插入自己的阶段，并为每个自定义阶段写 Prompt。</p>
        <div class="flow" id="phaseFlow"></div>
        <details id="customPhaseDetails" open>
          <summary class="foldHead"><span>自定义方法/阶段</span><span class="tiny" id="customPhaseCount">0 个</span></summary>
          <div class="foldBody">
            <div class="lockNote">基础研究流程会始终保留：范围、综述、数据、基线、方法、实验、证据、写作和内审。自定义阶段只作为额外检查点插入。</div>
            <div class="workflowEditor" id="workflowEditor"></div>
          </div>
        </details>
      </section>
      <section>
        <h2>Codex 现在在做什么</h2>
        <p class="muted" style="margin-bottom:10px">这里显示 Codex 自己写入的自然语言进展；没有原始日志，也不会按换行拆消息。</p>
        <div class="feed" id="feed"></div>
        <div class="composer">
          <textarea id="interventionText" placeholder="实时介入：输入你希望下一轮 Codex 采纳的新要求。需要立刻改变方向时先暂停。"></textarea>
          <button class="primary" id="sendInterventionBtn">发送</button>
        </div>
      </section>
    </div>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const roleName = {agent: 'Codex', human: '你', system: '系统'};
    let workflowDirty = false;
    let workflowPhases = [];
    let treeInitialized = false;
    const openTreeFolders = new Set();

    function setError(message) {
      $('errorBar').hidden = !message;
      $('errorBar').textContent = message || '';
    }
    async function api(path, options = {}) {
      try {
        const res = await fetch(path, {headers: {'content-type': 'application/json'}, ...options});
        if (!res.ok) throw new Error(await res.text());
        return await res.json();
      } catch (err) {
        setError(`连接或请求失败：${err.message || err}`);
        throw err;
      }
    }
    function esc(text) {
      return String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function formatMessageTime(ts) {
      if (!ts) return '';
      const date = new Date(ts);
      if (Number.isNaN(date.getTime())) return String(ts);
      return date.toLocaleString('zh-CN', {
        hour12: false,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
    }
    function ago(seconds) {
      if (seconds === null || seconds === undefined) return '-';
      if (seconds < 60) return `${seconds} 秒前`;
      if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
      return `${Math.floor(seconds / 3600)} 小时前`;
    }
    function compactNumber(value) {
      if (value === null || value === undefined) return '-';
      return Number(value).toLocaleString('zh-CN');
    }
    function percent(value) {
      if (value === null || value === undefined) return '-';
      return `${Math.round(Number(value) * 10) / 10}%`;
    }
    function windowLabel(minutes, fallback) {
      if (!minutes) return fallback;
      if (minutes % 1440 === 0) return `${minutes / 1440} 天余量`;
      if (minutes % 60 === 0) return `${minutes / 60} 小时余量`;
      return `${minutes} 分钟余量`;
    }
    function resetText(seconds) {
      if (seconds === null || seconds === undefined) return '';
      return `重置 ${ago(seconds)}后`;
    }
    function setQuotaBar(wrapId, barId, remaining) {
      const value = remaining === null || remaining === undefined ? 0 : Math.max(0, Math.min(100, Number(remaining)));
      $(barId).style.width = `${value}%`;
      $(wrapId).className = `quotaBar ${value < 20 ? 'low' : value < 50 ? 'mid' : ''}`;
    }
    function healthClass(health) {
      if (health === 'active') return 'active';
      if (health === 'waiting' || health === 'ready') return 'waiting';
      if (health === 'stopped' || health === 'error') return 'stopped';
      return '';
    }
    function routeDecisionLabel(decision) {
      return ({
        advance: '前进',
        repeat: '重做当前阶段',
        jump_back: '跳回',
        skip_next: '跳过下一阶段',
        jump_to: '跳转',
        skip_to: '跳转'
      })[decision] || (decision || '路由');
    }
    function phaseLabel(key) {
      const phase = workflowPhases.find(p => p.key === key);
      return phase ? `${phase.title} (${phase.key})` : (key || '-');
    }
    function routeLine(route) {
      const from = phaseLabel(route.from_phase);
      const to = phaseLabel(route.resolved_next_phase || route.target_phase);
      return `${routeDecisionLabel(route.decision)}：${from} -> ${to}`;
    }
    function renderRoutePanel(data) {
      const routes = Array.isArray(data.routes) ? data.routes : [];
      const panel = $('routePanel');
      if (!routes.length) {
        panel.hidden = true;
        return;
      }
      const latest = routes[routes.length - 1];
      panel.hidden = false;
      panel.className = `routePanel ${latest.ignored ? 'ignored' : ''}`;
      const summary = data.route_summary || {};
      $('routeCount').textContent = `${summary.total || routes.length} 次路由 / ${summary.jumps || 0} 次跳转`;
      const revisit = data.phase && data.phase.revisited ? `当前阶段第 ${data.phase.active_visit_count} 次进入。` : '';
      $('routeHeadline').textContent = latest.ignored ? `路由建议被忽略：${routeLine(latest)}` : routeLine(latest);
      $('routeSub').textContent = [latest.reason, latest.ignore_reason, revisit].filter(Boolean).join(' ');
      $('routeList').innerHTML = routes.slice().reverse().map((route, index) => {
        const confidence = route.confidence === null || route.confidence === undefined || route.confidence === '' ? '' : ` · 置信度 ${route.confidence}`;
        const ignored = route.ignored ? ' · 已忽略' : '';
        return `<div class="routeItem">
          <strong>${esc(routes.length - index)}. ${esc(routeLine(route))}</strong>
          <div class="routeMeta">${esc(route.decided_at || '')}${esc(confidence)}${esc(ignored)}</div>
          ${route.reason ? `<div>${esc(route.reason)}</div>` : ''}
          ${route.ignore_reason ? `<div class="routeMeta">${esc(route.ignore_reason)}</div>` : ''}
        </div>`;
      }).join('');
    }
    function buildFileTree(files) {
      const root = {path: '', name: '', dirs: new Map(), files: []};
      (files || []).forEach(file => {
        const parts = String(file.path || '').split('/').filter(Boolean);
        if (!parts.length) return;
        let node = root;
        let currentPath = '';
        parts.slice(0, -1).forEach(part => {
          currentPath = currentPath ? `${currentPath}/${part}` : part;
          if (!node.dirs.has(part)) node.dirs.set(part, {path: currentPath, name: part, dirs: new Map(), files: []});
          node = node.dirs.get(part);
        });
        node.files.push(file);
      });
      return root;
    }
    function treeFileCount(node) {
      let total = node.files.length;
      node.dirs.forEach(child => { total += treeFileCount(child); });
      return total;
    }
    function renderTreeChildren(node, depth) {
      const dirs = Array.from(node.dirs.values()).sort((a, b) => a.name.localeCompare(b.name));
      const files = node.files.slice().sort((a, b) => String(a.name).localeCompare(String(b.name)));
      const folderHtml = dirs.map(dir => renderTreeFolder(dir, depth)).join('');
      const fileHtml = files.map(file => {
        const name = file.name || String(file.path || '').split('/').pop() || file.path;
        return `<button class="file" data-path="${esc(file.path)}" title="${esc(file.path)}" style="padding-left:${8 + depth * 14}px"><span class="fileName">${esc(name)}</span><span class="fileKind">${esc(file.kind || 'file')}</span></button>`;
      }).join('');
      return folderHtml + fileHtml;
    }
    function renderTreeFolder(dir, depth) {
      const open = openTreeFolders.has(dir.path) ? 'open' : '';
      return `<details class="treeFolder" data-path="${esc(dir.path)}" ${open}>
        <summary style="padding-left:${8 + depth * 14}px"><span>${esc(dir.name)}</span><span class="treeCount">${treeFileCount(dir)}</span></summary>
        ${renderTreeChildren(dir, depth + 1)}
      </details>`;
    }
    function applyMemoryProfile(profile) {
      const presets = {
        focused: {summary:true, logs:false, human_interventions:true, artifact_index:false},
        balanced: {summary:true, logs:false, human_interventions:true, artifact_index:true},
        deep: {summary:true, logs:true, human_interventions:true, artifact_index:true},
        clean: {summary:false, logs:false, human_interventions:true, artifact_index:false}
      };
      const preset = presets[profile];
      if (!preset) return;
      $('memSummary').checked = preset.summary;
      $('memLogs').checked = preset.logs;
      $('memHuman').checked = preset.human_interventions;
      $('memArtifacts').checked = preset.artifact_index;
    }
    function basePhaseOptions(selected) {
      const bases = workflowPhases.filter(p => p.kind !== 'custom');
      return bases.map(p =>
        `<option value="${esc(p.key)}" ${p.key === selected ? 'selected' : ''}>${esc(p.title)}</option>`
      ).join('');
    }
    function workflowRowsFromDom() {
      return Array.from(document.querySelectorAll('.workflowRow.custom')).map(row => ({
        kind: 'custom',
        key: row.dataset.key || '',
        enabled: row.querySelector('[data-field="enabled"]').checked,
        title: row.querySelector('[data-field="title"]').value.trim(),
        insert_after: row.querySelector('[data-field="insert_after"]').value,
        prompt: row.querySelector('[data-field="prompt"]').value.trim(),
        objective: row.querySelector('[data-field="objective"]').value.trim(),
        gate: row.querySelector('[data-field="gate"]').value.trim()
      }));
    }
    function markWorkflowDirty() {
      workflowDirty = true;
    }
    function newCustomPhase() {
      return {
        kind: 'custom',
        key: `custom_${Date.now()}`,
        enabled: true,
        title: '自定义阶段',
        insert_after: workflowPhases.find(p => p.kind !== 'custom')?.key || 'scope',
        prompt: '',
        objective: '',
        gate: '',
        page_url: '#'
      };
    }
    function renderWorkflowEditor(phases) {
      workflowPhases = phases;
      const customCount = phases.filter(p => p.kind === 'custom').length;
      $('customPhaseCount').textContent = `${customCount} 个`;
      if (workflowDirty) return;
      const customs = phases.filter(p => p.kind === 'custom');
      if (!customs.length) {
        $('workflowEditor').innerHTML = '<div class="empty" style="min-height:90px">还没有自定义阶段。点击“添加阶段”，给 Codex 插入额外检查点或专项任务。</div>';
        return;
      }
      $('workflowEditor').innerHTML = customs.map(p => `
        <div class="workflowRow custom" data-key="${esc(p.key)}">
          <div class="workflowRowHeader">
            <label><input type="checkbox" data-field="enabled" ${p.enabled ? 'checked' : ''}> 启用</label>
            <input data-field="title" type="text" value="${esc(p.title)}" aria-label="阶段名称" placeholder="阶段名称">
            <select data-field="insert_after" aria-label="插入位置">${basePhaseOptions(p.insert_after || 'scope')}</select>
            <button data-remove="${esc(p.key)}">删除</button>
          </div>
          <textarea data-field="prompt" placeholder="这个阶段要交给 Codex 做什么。写清目标、输入、输出、判断标准。">${esc(p.prompt || '')}</textarea>
          <div class="grid2">
            <input data-field="objective" type="text" value="${esc(p.objective || '')}" placeholder="目标说明，可选">
            <input data-field="gate" type="text" value="${esc(p.gate || '')}" placeholder="完成门禁，可选">
          </div>
          <div class="row">
            <span class="tiny">默认产物：custom/${esc(p.key)}.md 和 reports/${esc(p.key)}.json</span>
            <button data-open="${esc(p.page_url)}">展示页</button>
          </div>
        </div>
      `).join('');
      document.querySelectorAll('.workflowRow').forEach(row => {
        row.querySelectorAll('input, textarea, select').forEach(input => {
          input.addEventListener('input', markWorkflowDirty);
          input.addEventListener('change', markWorkflowDirty);
        });
        row.querySelector('[data-remove]').addEventListener('click', event => {
          event.preventDefault();
          row.remove();
          markWorkflowDirty();
        });
        row.querySelector('[data-open]').addEventListener('click', event => {
          event.preventDefault();
          const url = event.currentTarget.dataset.open;
          if (url && url !== '#') window.open(url, '_blank');
        });
      });
    }
    function renderStatus(data) {
      $('researchDir').textContent = data.research_dir;
      $('phaseKey').textContent = `${data.phase.key} · ${data.phase.title}`;
      $('reportStatus').textContent = data.phase.display_status || data.phase.report_status;
      const job = data.job || {};
      const health = job.health || 'idle';
      const cls = healthClass(health);
      $('statusDot').className = `dot ${cls}`;
      $('headerState').className = `pill ${cls}`;
      $('headerState').textContent = job.state_label || '未运行';
      $('statusTitle').textContent = job.state_label || '未运行';
      $('statusSub').textContent = job.message || '后台没有运行任务';
      $('jobMode').textContent = job.mode || '无任务';
      $('pidValue').textContent = job.current_pid || '-';
      $('lastActivity').textContent = ago(job.last_activity && job.last_activity.age_seconds);
      $('startBtn').disabled = !!job.running;
      $('stopBtn').disabled = !job.running;
      workflowPhases = data.phases || [];
      $('phaseFlow').innerHTML = data.phases.map(p => {
        const kindText = p.kind === 'custom' ? '自定义' : '主干';
        const visit = p.active_visit_count > 1 ? ` · 第${p.active_visit_count}次` : '';
        return `<button class="phase ${p.status} ${p.kind === 'custom' ? 'custom' : ''} ${p.revisited ? 'revisited' : ''}" data-url="${esc(p.page_url)}"><strong>${esc(p.index)}. ${esc(p.title)}</strong><span class="phaseMeta">${esc(kindText)} · ${esc(p.status_text || p.status)} · ${esc(p.present_count || 0)}/${esc(p.required_count || 0)}${esc(visit)}</span></button>`;
      }).join('');
      document.querySelectorAll('.phase[data-url]').forEach(el => el.addEventListener('click', () => window.open(el.dataset.url, '_blank')));
      renderRoutePanel(data);
      renderWorkflowEditor(data.phases);
    }
    function renderCodexStatus(data) {
      if (!data.available) {
        $('codexPrimaryValue').textContent = '-';
        $('codexSecondaryValue').textContent = '-';
        $('codexPlan').textContent = '-';
        $('codexContext').textContent = '-';
        $('codexStatusMeta').textContent = data.message || '没有读到 Codex 状态';
        setQuotaBar('codexPrimaryBarWrap', 'codexPrimaryBar', 0);
        setQuotaBar('codexSecondaryBarWrap', 'codexSecondaryBar', 0);
        return;
      }
      const primary = data.primary || {};
      const secondary = data.secondary || {};
      $('codexPrimaryLabel').textContent = windowLabel(primary.window_minutes, '短周期余量');
      $('codexSecondaryLabel').textContent = windowLabel(secondary.window_minutes, '长周期余量');
      $('codexPrimaryValue').textContent = percent(primary.remaining_percent);
      $('codexSecondaryValue').textContent = percent(secondary.remaining_percent);
      setQuotaBar('codexPrimaryBarWrap', 'codexPrimaryBar', primary.remaining_percent);
      setQuotaBar('codexSecondaryBarWrap', 'codexSecondaryBar', secondary.remaining_percent);
      $('codexPlan').textContent = data.plan_type || '-';
      $('codexContext').textContent = data.model_context_window ? compactNumber(data.model_context_window) : '-';
      const total = data.total_token_usage || {};
      const source = data.source === 'active' ? '当前运行' : '最近会话';
      const reset = [resetText(primary.reset_in_seconds), resetText(secondary.reset_in_seconds)].filter(Boolean).join(' / ');
      $('codexStatusMeta').textContent = `${source} · 更新 ${ago(data.age_seconds)} · total ${compactNumber(total.total_tokens)} tokens${reset ? ' · ' + reset : ''}`;
    }
    function renderFeed(data) {
      const feed = $('feed');
      if (!data.messages.length) {
        feed.innerHTML = '<div class="empty">还没有 Codex 进展。启动后台任务后，这里会显示 Codex 自己写入的自然语言更新。</div>';
        return;
      }
      const bottomOffset = feed.scrollHeight - feed.scrollTop;
      const shouldFollow = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
      feed.innerHTML = data.messages.map(m => {
        const human = m.role === 'human';
        const files = Array.isArray(m.files) && m.files.length ? `<div class="meta">产物：${m.files.map(esc).join(', ')}</div>` : '';
        const time = formatMessageTime(m.ts);
        const meta = [m.phase, m.status, time ? `时间 ${time}` : ''].filter(Boolean).join(' · ');
        return `<div class="msg ${human ? 'human' : ''}">
          <span class="avatar">${roleName[m.role] || esc(m.role)}</span>
          <div class="bubble">${esc(m.text)}${meta ? `<div class="meta">${esc(meta)}</div>` : ''}${files}</div>
        </div>`;
      }).join('');
      if (shouldFollow) feed.scrollTop = feed.scrollHeight;
      else feed.scrollTop = Math.max(0, feed.scrollHeight - bottomOffset);
    }
    async function refreshProjects() {
      const data = await api('/api/projects');
      $('projectSelect').innerHTML = data.projects.map(p => {
        const run = p.running ? '运行中' : '空闲';
        const cur = p.current ? '当前' : run;
        return `<option value="${esc(p.research_dir)}" ${p.current ? 'selected' : ''}>${esc(p.name)} · ${esc(p.phase || '')} · ${esc(cur)}</option>`;
      }).join('');
    }
    async function refreshStatus() { renderStatus(await api('/api/status')); }
    async function refreshCodexStatus() { renderCodexStatus(await api('/api/codex/status')); }
    async function refreshFeed() { renderFeed(await api('/api/stream?limit=80')); }
    async function refreshTree() {
      const data = await api('/api/tree');
      $('fileTreeCount').textContent = `${data.files.length} 个`;
      if (!data.files.length) {
        $('fileTree').innerHTML = '<p class="muted" style="padding:8px">暂无文件</p>';
        return;
      }
      const tree = buildFileTree(data.files);
      if (!treeInitialized) {
        tree.dirs.forEach(dir => openTreeFolders.add(dir.path));
        treeInitialized = true;
      }
      $('fileTree').innerHTML = renderTreeChildren(tree, 0);
      document.querySelectorAll('.treeFolder[data-path]').forEach(el => {
        el.addEventListener('toggle', () => {
          if (el.open) openTreeFolders.add(el.dataset.path);
          else openTreeFolders.delete(el.dataset.path);
        });
      });
      document.querySelectorAll('.file[data-path]').forEach(el => {
        el.addEventListener('click', () => window.open('/preview?path=' + encodeURIComponent(el.dataset.path), '_blank'));
      });
    }
    async function refreshMemory() {
      const mem = await api('/api/memory');
      $('memoryProfile').value = mem.profile || 'balanced';
      $('memoryProfileText').textContent = mem.description || '';
      $('memSummary').checked = !!mem.summary;
      $('memLogs').checked = !!mem.logs;
      $('memHuman').checked = !!mem.human_interventions;
      $('memArtifacts').checked = !!mem.artifact_index;
    }
    async function refreshAll() {
      const results = await Promise.allSettled([refreshProjects(), refreshStatus(), refreshCodexStatus(), refreshFeed(), refreshTree(), refreshMemory()]);
      if (!results.some(item => item.status === 'rejected')) setError('');
    }
    async function switchProject(path) {
      try {
        await api('/api/project/switch', {method: 'POST', body: JSON.stringify({research_dir: path})});
        openTreeFolders.clear();
        treeInitialized = false;
        await refreshAll();
      } catch (err) {}
    }
    async function createProject() {
      const task = $('newProjectTask').value.trim();
      if (!task) {
        setError('新研究方向不能为空');
        return;
      }
      const btn = $('newProjectBtn');
      btn.disabled = true;
      btn.textContent = '创建中';
      try {
        await api('/api/project/create', {method: 'POST', body: JSON.stringify({
          task,
          name: $('newProjectName').value.trim()
        })});
        $('newProjectTask').value = '';
        $('newProjectName').value = '';
        openTreeFolders.clear();
        treeInitialized = false;
        await refreshAll();
      } finally {
        btn.disabled = false;
        btn.textContent = '新建并切换';
      }
    }
    $('refreshBtn').addEventListener('click', refreshAll);
    $('projectSelect').addEventListener('change', () => switchProject($('projectSelect').value));
    $('switchPathBtn').addEventListener('click', () => {
      const path = $('projectPathInput').value.trim();
      if (path) switchProject(path);
    });
    $('newProjectBtn').addEventListener('click', createProject);
    $('startBtn').addEventListener('click', async () => {
      const cycles = $('cyclesInput').value.trim();
      const duration = $('durationInput').value.trim();
      $('statusTitle').textContent = '正在启动后台任务';
      $('statusSub').textContent = cycles || duration ? '按设定条件运行，结束后可再次启动' : '持续运行中，关闭网页不影响进程';
      try {
        await api('/api/run/start', {method: 'POST', body: JSON.stringify({
          interval: Number($('intervalInput').value || 1800),
          cycles: cycles ? Number(cycles) : null,
          duration_minutes: duration ? Number(duration) : null,
          dry_run: $('dryRunInput').checked,
          codex_bin: $('codexInput').value || 'codex'
        })});
        await refreshAll();
      } catch (err) {}
    });
    $('stopBtn').addEventListener('click', async () => {
      $('statusTitle').textContent = '正在暂停';
      try {
        await api('/api/run/stop', {method: 'POST', body: '{}'});
        await refreshAll();
      } catch (err) {}
    });
    $('sendInterventionBtn').addEventListener('click', async () => {
      const message = $('interventionText').value.trim();
      if (!message) return;
      try {
        await api('/api/intervention', {method: 'POST', body: JSON.stringify({message})});
        $('interventionText').value = '';
        await refreshAll();
      } catch (err) {}
    });
    $('saveMemoryBtn').addEventListener('click', async () => {
      try {
        await api('/api/memory', {method: 'POST', body: JSON.stringify({
          profile: $('memoryProfile').value,
          summary: $('memSummary').checked,
          logs: $('memLogs').checked,
          human_interventions: $('memHuman').checked,
          artifact_index: $('memArtifacts').checked
        })});
        await refreshMemory();
      } catch (err) {}
    });
    $('memoryProfile').addEventListener('change', () => {
      applyMemoryProfile($('memoryProfile').value);
      const text = $('memoryProfile').selectedOptions[0]?.textContent || '';
      $('memoryProfileText').textContent = text === '自定义' ? '手动选择高级来源。' : '保存后下一轮 Codex 会按这个记忆模式读取上下文。';
    });
    $('addCustomPhaseBtn').addEventListener('click', () => {
      const current = workflowRowsFromDom();
      current.push(newCustomPhase());
      workflowDirty = false;
      renderWorkflowEditor([...workflowPhases.filter(p => p.kind !== 'custom'), ...current]);
      workflowDirty = true;
    });
    $('saveWorkflowBtn').addEventListener('click', async () => {
      try {
        await api('/api/workflow', {method: 'POST', body: JSON.stringify({phases: workflowRowsFromDom()})});
        workflowDirty = false;
        await refreshStatus();
      } catch (err) {}
    });
    $('resetWorkflowBtn').addEventListener('click', async () => {
      try {
        await api('/api/workflow', {method: 'POST', body: JSON.stringify({reset: true})});
        workflowDirty = false;
        await refreshStatus();
      } catch (err) {}
    });
    refreshAll();
    setInterval(() => {
      Promise.allSettled([refreshStatus(), refreshCodexStatus(), refreshFeed(), refreshTree()]).then(results => {
        if (!results.some(item => item.status === 'rejected')) setError('');
      });
    }, 2000);
  </script>
</body>
</html>
""".encode("utf-8")


class PaperFactoryHandler(BaseHTTPRequestHandler):
    root: Path
    manager: JobManager

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (now(), format % args))

    def send_payload(self, payload: bytes, content_type: str = "application/json", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, payload: Any, status: int = 200) -> None:
        self.send_payload(json_bytes(payload), "application/json; charset=utf-8", status)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"error": message}, status)

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)
            if path == "/":
                self.send_payload(index_html_cn_v3(), "text/html; charset=utf-8")
            elif path == "/api/status":
                payload = phase_payload(self.root)
                payload["job"] = self.manager.snapshot()
                self.send_json(payload)
            elif path == "/api/projects":
                self.send_json({"projects": discover_projects(self.root)})
            elif path == "/api/workflow":
                self.send_json({"phases": researchctl.workflow_config_for_ui(self.root)})
            elif path == "/api/codex/status":
                self.send_json(codex_status(self.root))
            elif path == "/api/logs":
                limit = int(query.get("limit", ["120"])[0])
                lines = []
                lines.extend(read_tail(researchctl.log_path(self.root), limit))
                lines.extend(read_tail(self.root / "logs" / "paperfactory-run.out", limit // 2))
                lines.extend(read_tail(self.root / "logs" / "codex-loop.out", limit // 2))
                lines.extend(read_tail(self.root / "logs" / "review.out", limit // 2))
                self.send_json({"lines": lines[-limit:]})
            elif path == "/api/stream":
                limit = int(query.get("limit", ["120"])[0])
                self.send_json({"messages": stream_messages(self.root, limit)})
            elif path == "/api/interventions":
                self.send_json({"text": read_interventions(self.root)})
            elif path == "/api/memory":
                self.send_json(read_memory_config(self.root))
            elif path == "/api/tree":
                self.send_json({"files": file_tree(self.root)})
            elif path == "/api/artifacts":
                self.send_json({"files": list_artifacts(self.root)})
            elif path == "/api/figures":
                self.send_json({"files": list_figures(self.root)})
            elif path == "/api/artifact":
                rel = query.get("path", [""])[0]
                self.send_json(artifact_preview(self.root, rel))
            elif path == "/preview":
                rel = query.get("path", [""])[0]
                self.send_payload(preview_html(self.root, rel), "text/html; charset=utf-8")
            elif path == "/phase":
                key = str(query.get("key", [""])[0])
                self.send_payload(phase_page_html(self.root, key), "text/html; charset=utf-8")
            elif path.startswith("/files/"):
                rel = safe_rel_path(path.removeprefix("/files/"))
                file_path = self.root / rel
                if not file_path.exists() or not file_path.is_file():
                    self.send_error_json(404, "File not found")
                    return
                content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                self.send_payload(file_path.read_bytes(), content_type)
            else:
                self.send_error_json(404, "Not found")
        except Exception as exc:
            self.send_error_json(500, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urllib.parse.urlparse(self.path)
            body = read_json_body(self)
            if parsed.path == "/api/task":
                task = str(body.get("task", "")).strip()
                if not task:
                    self.send_error_json(400, "task must not be empty")
                    return
                state = researchctl.load_state(self.root)
                state["task"] = task
                researchctl.write_state(self.root, state)
                (self.root / "task.md").write_text(f"# Initial Research Task\n\n{task}\n", encoding="utf-8")
                researchctl.append_log(self.root, "Web UI task updated")
                self.send_json({"ok": True})
            elif parsed.path == "/api/project/switch":
                new_root = normalize_research_root(str(body.get("research_dir") or ""))
                type(self).root = new_root
                self.manager.root = new_root
                payload = phase_payload(new_root)
                payload["job"] = self.manager.snapshot()
                self.send_json(payload)
            elif parsed.path == "/api/project/create":
                if not str(body.get("task") or "").strip():
                    self.send_error_json(400, "task must not be empty")
                    return
                created = create_research_project(
                    self.root,
                    task=str(body.get("task") or ""),
                    name=str(body.get("name") or ""),
                )
                new_root = Path(created["research_dir"]).resolve()
                type(self).root = new_root
                self.manager.root = new_root
                payload = phase_payload(new_root)
                payload["job"] = self.manager.snapshot()
                payload["created_project"] = created
                payload["projects"] = discover_projects(new_root)
                self.send_json(payload)
            elif parsed.path == "/api/prompt":
                prompt = write_next_prompt(self.root)
                self.send_json({"prompt": prompt, "path": "next_prompt.md"})
            elif parsed.path == "/api/intervention":
                message = str(body.get("message") or "")
                append_intervention(self.root, message)
                prompt = write_next_prompt(self.root)
                self.send_json({"ok": True, "prompt": prompt, "path": HUMAN_INTERVENTIONS})
            elif parsed.path == "/api/memory":
                self.send_json(write_memory_config(self.root, body))
            elif parsed.path == "/api/workflow":
                if body.get("reset"):
                    try:
                        researchctl.workflow_config_path(self.root).unlink()
                    except FileNotFoundError:
                        pass
                    rows = researchctl.workflow_config_for_ui(self.root)
                else:
                    raw_phases = body.get("custom_phases", body.get("phases"))
                    if not isinstance(raw_phases, list):
                        self.send_error_json(400, "phases/custom_phases must be a list")
                        return
                    rows = researchctl.write_workflow_config(self.root, raw_phases)
                enabled_keys = [str(item["key"]) for item in rows if item.get("enabled", True)]
                state = researchctl.load_state(self.root)
                if state.get("phase") != "complete" and str(state.get("phase")) not in enabled_keys:
                    state["phase"] = enabled_keys[0] if enabled_keys else "complete"
                    researchctl.write_state(self.root, state)
                researchctl.append_log(self.root, "Web UI workflow config updated")
                self.send_json({"phases": rows})
            elif parsed.path == "/api/run/start":
                ok, message = self.manager.start_loop(
                    self.root,
                    interval=int(body.get("interval") or 1800),
                    cycles=body.get("cycles"),
                    dry_run=bool(body.get("dry_run")),
                    codex_bin=str(body.get("codex_bin") or os.environ.get("CODEX_BIN", "codex")),
                    duration_minutes=int(body["duration_minutes"]) if body.get("duration_minutes") else None,
                )
                self.send_json({"ok": ok, "message": message}, 200 if ok else 409)
            elif parsed.path == "/api/run/stop":
                ok, message = self.manager.stop()
                self.send_json({"ok": ok, "message": message})
            elif parsed.path == "/api/review/prompt":
                prompt = build_review_prompt(
                    self.root,
                    venue=str(body.get("venue") or "top-tier ML/AI conference"),
                    draft_path=str(body.get("draft_path") or "paper/paper_draft.md"),
                    mode=str(body.get("mode") or "deep-review"),
                )
                prompt_path = self.root / "reviews" / "top_conference_review_prompt.md"
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(prompt, encoding="utf-8")
                researchctl.append_log(self.root, "Web UI top-conference review prompt generated")
                self.send_json({"prompt": prompt, "path": "reviews/top_conference_review_prompt.md"})
            elif parsed.path == "/api/review/start":
                prompt = build_review_prompt(
                    self.root,
                    venue=str(body.get("venue") or "top-tier ML/AI conference"),
                    draft_path=str(body.get("draft_path") or "paper/paper_draft.md"),
                    mode=str(body.get("mode") or "deep-review"),
                )
                ok, message = self.manager.start_review(
                    self.root,
                    venue=str(body.get("venue") or "top-tier ML/AI conference"),
                    draft_path=str(body.get("draft_path") or "paper/paper_draft.md"),
                    mode=str(body.get("mode") or "deep-review"),
                    dry_run=bool(body.get("dry_run")),
                    codex_bin=str(body.get("codex_bin") or os.environ.get("CODEX_BIN", "codex")),
                )
                self.send_json({"ok": ok, "message": message, "prompt": prompt}, 200 if ok else 409)
            else:
                self.send_error_json(404, "Not found")
        except ValueError as exc:
            self.send_error_json(400, str(exc))
        except Exception as exc:
            self.send_error_json(500, str(exc))


def make_handler(root: Path, manager: JobManager) -> type[PaperFactoryHandler]:
    class BoundHandler(PaperFactoryHandler):
        pass

    manager.root = root
    BoundHandler.root = root
    BoundHandler.manager = manager
    return BoundHandler


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-dir", default=researchctl.DEFAULT_RESEARCH_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the UI in the default browser")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.research_dir).expanduser().resolve()
    if not researchctl.state_path(root).exists():
        raise SystemExit(f"Research state not found: {researchctl.state_path(root)}. Run paperfactory new first.")
    manager = JobManager()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(root, manager))
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    print(f"PaperFactory Web UI: {url}")
    print(f"Research dir: {root}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        manager.stop()
        print("\nStopping PaperFactory Web UI.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
