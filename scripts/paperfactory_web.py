#!/usr/bin/env python3
"""Interactive local Web UI for Codex PaperFactory."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
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


def read_tail(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-limit:]


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
        with self.lock:
            return dict(self.status)

    def start_loop(self, root: Path, interval: int, cycles: int | None, dry_run: bool, codex_bin: str) -> tuple[bool, str]:
        with self.lock:
            if self.status.get("running"):
                return False, "A job is already running."
            self.stop_event.clear()
            self.status.update(
                {
                    "running": True,
                    "mode": "loop",
                    "started_at": datetime.now().astimezone().isoformat(),
                    "stopped_at": None,
                    "completed": 0,
                    "last_rc": None,
                    "dry_run": dry_run,
                    "message": "loop started",
                    "current_pid": None,
                }
            )
            self.thread = threading.Thread(
                target=self._loop_worker,
                args=(root, max(1, interval), cycles, dry_run, codex_bin),
                daemon=True,
            )
            self.thread.start()
            return True, "Loop started."

    def start_review(
        self,
        root: Path,
        venue: str,
        draft_path: str,
        mode: str,
        dry_run: bool,
        codex_bin: str,
    ) -> tuple[bool, str]:
        with self.lock:
            if self.status.get("running"):
                return False, "A job is already running."
            self.stop_event.clear()
            self.status.update(
                {
                    "running": True,
                    "mode": "review",
                    "started_at": datetime.now().astimezone().isoformat(),
                    "stopped_at": None,
                    "completed": 0,
                    "last_rc": None,
                    "dry_run": dry_run,
                    "message": "review started",
                    "current_pid": None,
                }
            )
            self.thread = threading.Thread(
                target=self._review_worker,
                args=(root, venue, draft_path, mode, dry_run, codex_bin),
                daemon=True,
            )
            self.thread.start()
            return True, "Review started."

    def stop(self) -> tuple[bool, str]:
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
                self.send_payload(index_html(), "text/html; charset=utf-8")
            elif path == "/api/status":
                payload = phase_payload(self.root)
                payload["job"] = self.manager.snapshot()
                self.send_json(payload)
            elif path == "/api/logs":
                limit = int(query.get("limit", ["120"])[0])
                lines = []
                lines.extend(read_tail(researchctl.log_path(self.root), limit))
                lines.extend(read_tail(self.root / "logs" / "codex-loop.out", limit // 2))
                lines.extend(read_tail(self.root / "logs" / "review.out", limit // 2))
                self.send_json({"lines": lines[-limit:]})
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
            elif parsed.path == "/api/run/start":
                ok, message = self.manager.start_loop(
                    self.root,
                    interval=int(body.get("interval") or 1800),
                    cycles=body.get("cycles"),
                    dry_run=bool(body.get("dry_run")),
                    codex_bin=str(body.get("codex_bin") or os.environ.get("CODEX_BIN", "codex")),
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
