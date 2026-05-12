#!/usr/bin/env python3
"""Interactive local Web UI for Codex PaperFactory."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
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


def pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
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


def default_memory_config() -> dict[str, bool]:
    return {
        "summary": True,
        "logs": True,
        "human_interventions": True,
        "artifact_index": True,
    }


def read_memory_config(root: Path) -> dict[str, bool]:
    config = default_memory_config()
    path = memory_config_path(root)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}
        if isinstance(raw, dict):
            for key in config:
                if key in raw:
                    config[key] = bool(raw[key])
    return config


def write_memory_config(root: Path, config: dict[str, Any]) -> dict[str, bool]:
    current = read_memory_config(root)
    for key in current:
        if key in config:
            current[key] = bool(config[key])
    memory_config_path(root).write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    researchctl.append_log(root, "Web UI memory config updated")
    return current


def stream_messages(root: Path, limit: int = 120) -> list[dict[str, str]]:
    events = read_progress_feed(root, limit)
    if not events:
        return [
            {
                "role": "system",
                "text": "等待 Codex 写入进展。启动任务后，Codex 会把自然语言进展追加到 .research/progress/feed.jsonl。",
            }
        ]
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


def phase_payload(root: Path) -> dict[str, Any]:
    state = researchctl.load_state(root)
    phase = researchctl.current_phase(state)
    phase_key = "complete" if phase is None else phase.key
    done, total = progress(phase_key)
    history = {item.get("phase") for item in state.get("phase_history", [])}
    phases = []
    for index, item in enumerate(researchctl.PHASES, 1):
        if phase_key == "complete" or item.key in history:
            status = "complete"
        elif item.key == phase_key:
            status = "current"
        else:
            status = "pending"
        phases.append(
            {
                "index": index,
                "key": item.key,
                "title": item.title,
                "objective": item.objective,
                "status": status,
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
        for rel in phase.required:
            path = root / rel
            required.append(
                {
                    "path": rel,
                    "present": path.exists() and path.stat().st_size > 0,
                    "size": path.stat().st_size if path.exists() else 0,
                    "url": f"/files/{urllib.parse.quote(rel)}" if path.exists() else None,
                }
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
            "missing": missing,
            "required": required,
        },
        "progress": {"current": done, "total": total},
        "phases": phases,
        "interventions": read_interventions(root),
    }


def progress(phase_key: str) -> tuple[int, int]:
    total = len(researchctl.PHASES)
    if phase_key == "complete":
        return total, total
    for index, phase in enumerate(researchctl.PHASES, 1):
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
- Run the bundled manuscript checker when the draft is Markdown, LaTeX, or Typst.
- Review as a top-conference area reviewer: novelty, related work, method clarity, experimental protocol, baseline fairness, statistics, ablations, limitations, reproducibility, ethics, and claim support.
- Do not rewrite the paper. Produce a decision-oriented review and required revision roadmap.
- Do not invent missing experiments, citations, line numbers, metrics, or reviewer consensus.
- Mark each issue as blocker, major, moderate, or minor.
- Include concrete fixes and whether new experiments are required.
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
            with self.lock:
                proc = self.process
            if proc is not None and proc.pid == pid:
                running = proc.poll() is None
            else:
                running = pid_running(pid)
            if job:
                job["running"] = running
                if not running and job.get("status") == "running":
                    job["status"] = "finished_or_stopped"
                    job["stopped_at"] = job.get("stopped_at") or datetime.now().astimezone().isoformat()
                    write_job(self.root, job)
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
                }
        with self.lock:
            return dict(self.status)

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
        elif cycles is None:
            cmd.extend(["--until", "2099-01-01 00:00:00"])
        else:
            cmd.extend(["--cycles", str(max(1, int(cycles)))])
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
                "message": "后台长跑中，关闭网页不影响进程",
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
            <label>Cycles <input id="cyclesInput" type="number" min="1" value="1" style="width:90px"></label>
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
          <label>轮数<input id="cyclesInput" type="number" min="1" value="1"></label>
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
          <label>轮数<input id="cyclesInput" type="number" min="1" value="1"></label>
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

    async function api(path, options = {}) {
      const res = await fetch(path, {headers: {'content-type': 'application/json'}, ...options});
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }
    function esc(text) {
      return String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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
      $('feed').innerHTML = data.messages.map(m => {
        const human = m.role === 'human';
        const files = Array.isArray(m.files) && m.files.length ? `<div class="meta">产物：${m.files.map(esc).join(', ')}</div>` : '';
        const meta = [m.phase, m.status].filter(Boolean).join(' · ');
        return `<div class="msg ${human ? 'human' : ''}">
          <span class="avatar">${roleName[m.role] || m.role}</span>
          <div class="bubble">${esc(m.text)}${meta ? `<div class="meta">${esc(meta)}</div>` : ''}${files}</div>
        </div>`;
      }).join('');
      $('feed').scrollTop = $('feed').scrollHeight;
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
                self.send_payload(index_html_cn_v2(), "text/html; charset=utf-8")
            elif path == "/api/status":
                payload = phase_payload(self.root)
                payload["job"] = self.manager.snapshot()
                self.send_json(payload)
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
