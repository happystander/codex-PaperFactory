#!/usr/bin/env python3
"""Convenience launcher and local UI for Codex PaperFactory."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

import researchctl


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_PROMPT_FILE = "next_prompt.md"
DEFAULT_DASHBOARD_FILE = "dashboard.html"


def resolve_research_dir(value: str) -> Path:
    return Path(value).expanduser().resolve()


def status_label(path: Path) -> str:
    return "OK" if path.exists() and path.stat().st_size > 0 else "MISSING"


def phase_progress(root: Path, phase_key: str) -> tuple[int, int]:
    phases = researchctl.configured_phases(root)
    total = len(phases)
    if phase_key == "complete":
        return total, total
    for index, phase in enumerate(phases, 1):
        if phase.key == phase_key:
            return index, total
    return 0, total


def progress_bar(done: int, total: int, width: int = 28) -> str:
    filled = 0 if total <= 0 else round(width * done / total)
    return "[" + "#" * filled + "." * (width - filled) + f"] {done}/{total}"


def load_state_or_exit(root: Path) -> dict[str, Any]:
    return researchctl.load_state(root)


def recent_log_lines(root: Path, limit: int = 8) -> list[str]:
    path = researchctl.log_path(root)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-limit:]


def relative_or_name(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def write_next_prompt(root: Path, output: Path | None = None) -> Path:
    state = load_state_or_exit(root)
    prompt = researchctl.build_next_prompt(root, state)
    target = output or (root / DEFAULT_PROMPT_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(prompt, encoding="utf-8")
    return target


def codex_workdir(root: Path) -> Path:
    if root.name == ".research":
        return root.parent
    return root


def copy_to_clipboard(text: str) -> bool:
    candidates = [
        ("pbcopy", []),
        ("wl-copy", []),
        ("xclip", ["-selection", "clipboard"]),
        ("xsel", ["--clipboard", "--input"]),
    ]
    for cmd, extra in candidates:
        if not shutil.which(cmd):
            continue
        proc = subprocess.run(
            [cmd, *extra],
            input=text,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return proc.returncode == 0
    return False


def command_new(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args.research_dir)
    task = args.task
    if not task and sys.stdin.isatty():
        task = input("Initial research task: ").strip()
    if not task:
        raise SystemExit("--task is required in non-interactive use")

    researchctl.command_init(argparse.Namespace(research_dir=str(root), task=task, force=args.force))
    prompt_path = write_next_prompt(root)
    dashboard_path = build_dashboard(root, args.dashboard_output)
    print()
    print("PaperFactory project is ready.")
    print(f"- State: {root}")
    print(f"- Prompt: {relative_or_name(prompt_path)}")
    print(f"- Dashboard: {relative_or_name(dashboard_path)}")
    print()
    launcher = ROOT / "paperfactory"
    print("Next commands:")
    print(f"  {launcher} status --research-dir {root}")
    print(f"  {launcher} run --once --research-dir {root}")
    print(f"  {launcher} dashboard --open --research-dir {root}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args.research_dir)
    state = load_state_or_exit(root)
    phase = researchctl.current_phase(state, root)
    phase_key = "complete" if phase is None else phase.key
    done, total = phase_progress(root, phase_key)

    if args.json:
        payload = {
            "research_dir": str(root),
            "task": state.get("task", ""),
            "phase": phase_key,
            "progress": {"current": done, "total": total},
            "updated_at": state.get("updated_at"),
        }
        if phase is not None:
            payload["report_status"] = researchctl.report_status(root, phase)
            payload["missing"] = researchctl.missing_required(root, phase)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("Codex PaperFactory")
    print("=" * 19)
    print(f"Research dir : {root}")
    print(f"Task         : {state.get('task', '')}")
    print(f"Updated      : {state.get('updated_at', 'unknown')}")
    print(f"Progress     : {progress_bar(done, total)}")

    if phase is None:
        print("Phase        : complete")
        return 0

    report_status = researchctl.report_status(root, phase) or "missing"
    missing = set(researchctl.missing_required(root, phase))
    print(f"Phase        : {phase.key} - {phase.title}")
    print(f"Report       : {report_status}")
    print(f"Gate         : {phase.gate}")
    print()
    print("Artifacts")
    for rel in phase.required:
        marker = "MISSING" if rel in missing else "OK"
        print(f"  {marker:7} {rel}")
    print()
    if missing:
        print("Next action  : create the missing artifacts, then run ./paperfactory prompt")
    else:
        print("Next action  : run ./paperfactory advance or ./paperfactory run --once")

    if args.logs:
        print()
        print("Recent Log")
        for line in recent_log_lines(root, args.logs):
            print(f"  {line}")
    return 0


def command_prompt(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args.research_dir)
    output = Path(args.output).expanduser().resolve() if args.output else None
    prompt_path = write_next_prompt(root, output)
    prompt = prompt_path.read_text(encoding="utf-8")
    if args.stdout:
        print(prompt)
    else:
        print(f"Wrote next prompt: {relative_or_name(prompt_path)}")
    if args.copy:
        copied = copy_to_clipboard(prompt)
        print("Copied to clipboard." if copied else "Clipboard tool not found; use the prompt file.")
    return 0


def file_link(root: Path, rel: str) -> str:
    safe_rel = html.escape(rel)
    return f'<a href="{safe_rel}">{safe_rel}</a>'


def phase_rows(root: Path, current_key: str) -> str:
    rows = []
    completed = {item.get("phase") for item in load_state_or_exit(root).get("phase_history", [])}
    for index, phase in enumerate(researchctl.configured_phases(root), 1):
        if phase.key == current_key:
            state = "current"
        elif phase.key in completed or current_key == "complete":
            state = "complete"
        else:
            state = "pending"
        kind = "custom" if phase.kind == "custom" else "base"
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><strong>{html.escape(phase.key)}</strong><br><span>{html.escape(phase.title)} · {kind}</span></td>"
            f'<td><span class="pill {state}">{state}</span></td>'
            f"<td>{html.escape(phase.objective)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def artifact_rows(root: Path, phase: researchctl.Phase | None) -> str:
    if phase is None:
        return '<tr><td colspan="3">Workflow complete.</td></tr>'
    rows = []
    for rel in phase.required:
        full = root / rel
        label = status_label(full)
        rows.append(
            "<tr>"
            f'<td><span class="pill {label.lower()}">{label}</span></td>'
            f"<td>{file_link(root, rel)}</td>"
            f"<td>{full.stat().st_size if full.exists() else 0}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_dashboard_html(root: Path, state: dict[str, Any]) -> str:
    phase = researchctl.current_phase(state, root)
    phase_key = "complete" if phase is None else phase.key
    done, total = phase_progress(root, phase_key)
    missing_count = 0 if phase is None else len(researchctl.missing_required(root, phase))
    report_status = "complete" if phase is None else (researchctl.report_status(root, phase) or "missing")
    logs = recent_log_lines(root, 12)
    log_items = "\n".join(f"<li>{html.escape(line)}</li>" for line in logs) or "<li>No log entries yet.</li>"
    task = html.escape(str(state.get("task", "")))
    phase_title = "Complete" if phase is None else html.escape(phase.title)
    gate = "No active gate." if phase is None else html.escape(phase.gate)
    updated = html.escape(str(state.get("updated_at", "unknown")))
    launcher = html.escape(str(ROOT / "paperfactory"))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex PaperFactory Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fb;
      --panel: #ffffff;
      --line: #d8dee8;
      --text: #172033;
      --muted: #5d6b82;
      --blue: #2563eb;
      --green: #0f8a5f;
      --amber: #b7791f;
      --red: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    header {{
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    main, .inner {{
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
    }}
    .inner {{ padding: 22px 0; }}
    h1 {{ margin: 0 0 6px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; letter-spacing: 0; }}
    p {{ margin: 0; }}
    a {{ color: var(--blue); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .muted {{ color: var(--muted); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 18px 0;
    }}
    .metric, section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .metric {{ padding: 14px; min-height: 92px; }}
    .metric .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .metric .value {{ font-size: 22px; font-weight: 700; margin-top: 8px; overflow-wrap: anywhere; }}
    section {{ padding: 18px; margin: 16px 0; }}
    .bar {{
      width: 100%;
      height: 12px;
      border-radius: 999px;
      background: #e8edf5;
      overflow: hidden;
      margin-top: 10px;
    }}
    .bar span {{
      display: block;
      height: 100%;
      width: {0 if total == 0 else round(done * 100 / total)}%;
      background: var(--blue);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }}
    th {{ font-size: 12px; color: var(--muted); text-transform: uppercase; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid transparent;
    }}
    .pill.complete, .pill.ok {{ color: var(--green); background: #eaf7f1; border-color: #bce4d2; }}
    .pill.current {{ color: var(--blue); background: #eaf1ff; border-color: #b8cdfd; }}
    .pill.pending {{ color: var(--muted); background: #eef2f7; border-color: #d8dee8; }}
    .pill.missing {{ color: var(--red); background: #fff0ee; border-color: #ffc9c2; }}
    .commands {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    code {{
      display: block;
      padding: 10px;
      border-radius: 6px;
      background: #111827;
      color: #f9fafb;
      overflow-x: auto;
      white-space: pre-wrap;
    }}
    ul {{ margin: 0; padding-left: 20px; }}
    @media (max-width: 820px) {{
      .grid, .commands {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 24px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="inner">
      <h1>Codex PaperFactory</h1>
      <p class="muted">{task}</p>
    </div>
  </header>
  <main>
    <div class="grid">
      <div class="metric"><div class="label">Phase</div><div class="value">{html.escape(phase_key)}</div></div>
      <div class="metric"><div class="label">Status</div><div class="value">{html.escape(report_status)}</div></div>
      <div class="metric"><div class="label">Progress</div><div class="value">{done}/{total}</div><div class="bar"><span></span></div></div>
      <div class="metric"><div class="label">Missing Artifacts</div><div class="value">{missing_count}</div></div>
    </div>
    <section>
      <h2>Current Gate</h2>
      <p><strong>{phase_title}</strong></p>
      <p class="muted">{gate}</p>
      <p class="muted">Updated: {updated}</p>
    </section>
    <section>
      <h2>Required Artifacts</h2>
      <table>
        <thead><tr><th>Status</th><th>Artifact</th><th>Bytes</th></tr></thead>
        <tbody>{artifact_rows(root, phase)}</tbody>
      </table>
    </section>
    <section>
      <h2>Workflow</h2>
      <table>
        <thead><tr><th>#</th><th>Phase</th><th>State</th><th>Objective</th></tr></thead>
        <tbody>{phase_rows(root, phase_key)}</tbody>
      </table>
    </section>
    <section>
      <h2>Recent Log</h2>
      <ul>{log_items}</ul>
    </section>
    <section>
      <h2>Commands</h2>
      <div class="commands">
        <code>{launcher} status --logs 8</code>
        <code>{launcher} prompt --copy</code>
        <code>{launcher} run --once</code>
        <code>{launcher} dashboard --open</code>
      </div>
    </section>
  </main>
</body>
</html>
"""


def build_dashboard(root: Path, output: str | None = None) -> Path:
    state = load_state_or_exit(root)
    target = Path(output).expanduser().resolve() if output else root / DEFAULT_DASHBOARD_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_dashboard_html(root, state), encoding="utf-8")
    return target


def command_dashboard(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args.research_dir)
    target = build_dashboard(root, args.output)
    print(f"Wrote dashboard: {relative_or_name(target)}")
    if args.open:
        webbrowser.open(target.as_uri())
    return 0


def parse_until(value: str) -> float:
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError as exc:
        raise SystemExit("--until must be ISO-like, e.g. '2026-05-15 10:00:00'") from exc


def run_codex_cycle(root: Path, codex_bin: str, dry_run: bool) -> int:
    prompt_path = write_next_prompt(root)
    prompt = prompt_path.read_text(encoding="utf-8")
    if dry_run:
        print(f"Dry run: wrote prompt to {relative_or_name(prompt_path)}")
        return 0

    log_file = root / "logs" / "codex-loop.out"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    workdir = codex_workdir(root)
    workdir.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"\n[{researchctl.now()}] PaperFactory cycle start\n")
        handle.write(f"[{researchctl.now()}] Codex workdir: {workdir}\n")
        handle.flush()
        proc = subprocess.run(
            [codex_bin, "exec", "--full-auto", "--skip-git-repo-check", prompt],
            cwd=workdir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        handle.write(f"[{researchctl.now()}] PaperFactory cycle rc={proc.returncode}\n")
    if proc.returncode != 0:
        researchctl.append_log(root, f"Codex cycle failed: rc={proc.returncode}")
    return int(proc.returncode)


def command_run(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args.research_dir)
    if not researchctl.state_path(root).exists():
        if not args.task:
            raise SystemExit(f"No {researchctl.state_path(root)} found. Provide --task to initialize.")
        researchctl.command_init(argparse.Namespace(research_dir=str(root), task=args.task, force=False))

    if args.once:
        cycles = 1
    elif args.cycles is not None:
        cycles = args.cycles
    elif args.until:
        cycles = None
    else:
        cycles = 1

    stop_at = parse_until(args.until) if args.until else None
    completed = 0
    while True:
        state = researchctl.load_state(root)
        stop = researchctl.stop_decision(root, state)
        if stop.get("should_stop"):
            researchctl.append_log(root, f"Loop stop: control decision reasons={stop.get('reasons')}")
            print(f"Stopped by control conditions: {', '.join(stop.get('reasons') or [])}")
            break
        if stop_at is not None and time.time() >= stop_at:
            researchctl.append_log(root, f"Loop stop: reached until={args.until}")
            break
        if cycles is not None and completed >= cycles:
            break
        rc = run_codex_cycle(root, args.codex_bin, args.dry_run)
        completed += 1
        cycle_state = researchctl.load_state(root)
        cycle_state.setdefault("cycles", []).append(
            {
                "completed_at": researchctl.iso_now(),
                "returncode": rc,
                "dry_run": bool(args.dry_run),
                "mode": "paperfactory run",
            }
        )
        researchctl.write_state(root, cycle_state)
        researchctl.refresh_runtime(root, cycle_state)
        if args.dry_run or rc != 0:
            return rc
        if cycles is not None and completed >= cycles:
            break
        time.sleep(args.interval)
    print(f"Completed {completed} cycle(s).")
    return 0


def command_advance(args: argparse.Namespace) -> int:
    return researchctl.command_advance(argparse.Namespace(research_dir=args.research_dir, force=args.force))


def command_validate(args: argparse.Namespace) -> int:
    return researchctl.command_validate(argparse.Namespace(research_dir=args.research_dir))


def command_log(args: argparse.Namespace) -> int:
    return researchctl.command_log(args)


def command_memory(args: argparse.Namespace) -> int:
    return researchctl.command_memory(argparse.Namespace(research_dir=args.research_dir, json=args.json))


def command_runtime(args: argparse.Namespace) -> int:
    return researchctl.command_runtime(argparse.Namespace(research_dir=args.research_dir, json=args.json))


def command_evidence(args: argparse.Namespace) -> int:
    return researchctl.command_evidence(argparse.Namespace(research_dir=args.research_dir, json=args.json))


def command_queue(args: argparse.Namespace) -> int:
    return researchctl.command_queue(argparse.Namespace(research_dir=args.research_dir, json=args.json))


def command_control(args: argparse.Namespace) -> int:
    return researchctl.command_control(argparse.Namespace(research_dir=args.research_dir, json=args.json))


def command_intervention(args: argparse.Namespace) -> int:
    return researchctl.command_intervention(
        argparse.Namespace(research_dir=args.research_dir, message=args.message, kind=args.kind, json=args.json)
    )


def command_web(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        str(SCRIPTS / "paperfactory_web.py"),
        "--research-dir",
        args.research_dir,
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.open:
        cmd.append("--open")
    return subprocess.call(cmd)


def append_binary_check(
    checks: list[tuple[str, str, str]],
    label: str,
    binary: str,
    purpose: str,
    *,
    required: bool = False,
) -> None:
    found = shutil.which(binary)
    if found:
        checks.append((label, "OK", found))
    else:
        status = "ERROR" if required else "WARN"
        checks.append((label, status, f"optional; install `{binary}` for {purpose}"))


def append_python_package_check(
    checks: list[tuple[str, str, str]],
    label: str,
    module: str,
    purpose: str,
    *,
    package: str | None = None,
    required: bool = False,
) -> None:
    if importlib.util.find_spec(module):
        checks.append((label, "OK", f"Python module `{module}` available"))
    else:
        status = "ERROR" if required else "WARN"
        install_name = package or module
        checks.append((label, status, f"optional; `pip install {install_name}` for {purpose}"))


def command_doctor(args: argparse.Namespace) -> int:
    del args
    checks: list[tuple[str, str, str]] = []
    checks.append(("python", "OK", sys.version.split()[0]))
    checks.append(("plugin root", "OK" if (ROOT / ".codex-plugin" / "plugin.json").exists() else "ERROR", str(ROOT)))
    for binary in ("git", "codex", "node"):
        found = shutil.which(binary)
        checks.append((binary, "OK" if found else "WARN", found or "not found on PATH"))
    try:
        json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        checks.append(("plugin manifest", "OK", ".codex-plugin/plugin.json"))
    except Exception as exc:
        checks.append(("plugin manifest", "ERROR", str(exc)))
    try:
        import matplotlib  # type: ignore  # noqa: F401

        checks.append(("matplotlib", "OK", "available for plot helper"))
    except Exception:
        checks.append(("matplotlib", "WARN", "not installed; plotting helper will fail"))

    local_skill_names = (
        "academic-polishing",
        "autonomous-research",
        "citation-workflow",
        "conference-paper-writing",
        "conference-page-budget",
        "data-availability",
        "best-paper-writing-reference",
        "latex-typst-paper",
        "llm-rl-toolkit",
        "manuscript-audit",
        "paper-format-self-check",
        "paper-reader",
        "presentation-deck",
        "research-library-workflow",
        "reviewer-response",
        "scientific-figure",
        "scientific-runtime-tooling",
    )
    for skill_name in local_skill_names:
        skill_file = ROOT / "skills" / skill_name / "SKILL.md"
        checks.append(
            (
                f"local:{skill_name}",
                "OK" if skill_file.exists() else "ERROR",
                str(skill_file) if skill_file.exists() else "missing plugin-local skill",
            )
        )

    skills_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills"
    latex_skill_names = (
        "paper-from-zero",
        "arxiv-paper-writer",
        "empirical-paper-writer",
        "latex-rhythm-refiner",
        "results-backfill",
        "drawio-academic-skills",
    )
    for skill_name in latex_skill_names:
        skill_file = skills_root / skill_name / "SKILL.md"
        checks.append(
            (
                f"skill:{skill_name}",
                "OK" if skill_file.exists() else "WARN",
                str(skill_file) if skill_file.exists() else "install from yunshenwuchuxun/latex-paper-skills",
            )
        )
    shared_utils = skills_root / "_shared" / "paper_utils.py"
    checks.append(
        (
            "skill:_shared",
            "OK" if shared_utils.exists() else "WARN",
            str(shared_utils) if shared_utils.exists() else "required by latex-paper-skills scripts",
        )
    )
    drawio_cli = skills_root / "drawio-academic-skills" / "scripts" / "cli.js"
    drawio_detail = str(drawio_cli) if drawio_cli.exists() else "drawio-academic-skills CLI not installed"
    drawio_status = "OK" if drawio_cli.exists() else "WARN"
    node_bin = shutil.which("node")
    if drawio_cli.exists() and node_bin:
        try:
            proc = subprocess.run(
                [node_bin, str(drawio_cli), "--help"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
                check=False,
            )
            if proc.returncode != 0:
                drawio_status = "WARN"
                drawio_detail = (proc.stderr or proc.stdout).strip().splitlines()[0][:120]
        except Exception as exc:
            drawio_status = "WARN"
            drawio_detail = str(exc)
    checks.append(
        (
            "drawio cli",
            drawio_status,
            drawio_detail,
        )
    )

    research_binaries = (
        ("tool:library:scholaraio", "scholaraio", "structured paper search, workspaces, citation checks, and scientific tool references"),
        ("tool:paper:pandoc", "pandoc", "Markdown/LaTeX/DOCX conversion"),
        ("tool:paper:libreoffice", "libreoffice", "Office document export and inspection"),
        ("tool:paper:latexmk", "latexmk", "repeatable LaTeX builds"),
        ("tool:paper:pdflatex", "pdflatex", "fallback PDF compilation"),
        ("tool:paper:tectonic", "tectonic", "self-contained LaTeX builds"),
        ("tool:paper:biber", "biber", "BibLaTeX bibliography builds"),
        ("tool:paper:bibtex", "bibtex", "BibTeX bibliography builds"),
        ("tool:diagram:dot", "dot", "Graphviz diagram rendering"),
        ("tool:diagram:inkscape", "inkscape", "SVG/PDF figure conversion and inspection"),
        ("tool:pdf:pdftotext", "pdftotext", "fast local PDF text extraction"),
        ("tool:pdf:grobid", "grobid_client", "structured scholarly PDF extraction"),
        ("tool:pdf:java", "java", "running GROBID or Java PDF tooling"),
        ("tool:lit:jq", "jq", "metadata API response inspection"),
        ("tool:lit:curl", "curl", "OpenAlex/Crossref/arXiv/Semantic Scholar API queries"),
        ("tool:lit:wget", "wget", "paper and dataset downloads"),
        ("tool:repro:dvc", "dvc", "data/model artifact versioning"),
        ("tool:repro:git-lfs", "git-lfs", "large artifact pointers in Git"),
        ("tool:track:mlflow", "mlflow", "experiment tracking UI and run metadata"),
        ("tool:flow:snakemake", "snakemake", "reproducible experiment workflows"),
    )
    for label, binary, purpose in research_binaries:
        append_binary_check(checks, label, binary, purpose)

    research_packages = (
        ("pkg:lit:arxiv", "arxiv", "arXiv API search helpers", "arxiv"),
        ("pkg:lit:habanero", "habanero", "Crossref API helpers", "habanero"),
        ("pkg:lit:semantic", "semanticscholar", "Semantic Scholar API helpers", "semanticscholar"),
        ("pkg:doc:markitdown", "markitdown", "Office/document-to-Markdown conversion", "markitdown"),
        ("pkg:pdf:pypdf", "pypdf", "fallback PDF metadata/text extraction", "pypdf"),
        ("pkg:pdf:pdfminer", "pdfminer", "fallback PDF layout/text extraction", "pdfminer.six"),
        ("pkg:topic:bertopic", "bertopic", "topic clustering for literature workspaces", "bertopic"),
        ("pkg:config:hydra", "hydra", "composable experiment configuration", "hydra-core"),
        ("pkg:config:omegaconf", "omegaconf", "typed experiment configuration", "omegaconf"),
        ("pkg:llm:trl", "trl", "Hugging Face post-training trainers", "trl"),
        ("pkg:llm:ms-swift", "swift", "ModelScope fine-tuning/RL full pipeline", "ms-swift"),
        ("pkg:llm:verl", "verl", "large-scale LLM RL post-training", "git+https://github.com/verl-project/verl.git"),
    )
    for label, module, purpose, package in research_packages:
        append_python_package_check(checks, label, module, purpose, package=package)

    reference_manifest = ROOT / "reference_papers" / "manifest.json"
    checks.append(
        (
            "refs:best-paper",
            "OK" if reference_manifest.exists() else "ERROR",
            str(reference_manifest) if reference_manifest.exists() else "missing curated best-paper manifest",
        )
    )
    reference_cache = ROOT / "reference_papers" / "cache"
    cached_papers = sorted(reference_cache.glob("*/metadata.json")) if reference_cache.exists() else []
    checks.append(
        (
            "refs:cache",
            "OK" if cached_papers else "WARN",
            f"{len(cached_papers)} cached paper(s); run scripts/fetch_best_paper_references.py" if cached_papers else "optional; run scripts/fetch_best_paper_references.py",
        )
    )

    for name, status, detail in checks:
        print(f"{status:5} {name:22} {detail}")
    return 1 if any(status == "ERROR" for _, status, _ in checks) else 0


def command_delegate(script_name: str, tool_args: list[str]) -> int:
    if tool_args and tool_args[0] == "--":
        tool_args = tool_args[1:]
    if not tool_args:
        tool_args = ["--help"]
    script = SCRIPTS / script_name
    return subprocess.call([sys.executable, str(script), *tool_args])


def add_research_dir_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--research-dir",
        default=argparse.SUPPRESS,
        help="Research state directory",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Friendly CLI and local dashboard for Codex PaperFactory.")
    parser.add_argument("--research-dir", default=researchctl.DEFAULT_RESEARCH_DIR, help="Research state directory")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="Initialize a project and generate prompt/dashboard files")
    add_research_dir_arg(new)
    new.add_argument("--task", help="Initial research task")
    new.add_argument("--force", action="store_true", help="Overwrite existing state")
    new.add_argument("--dashboard-output", help="Optional dashboard output path")
    new.set_defaults(func=command_new)

    status = sub.add_parser("status", help="Show a readable terminal status panel")
    add_research_dir_arg(status)
    status.add_argument("--json", action="store_true", help="Emit machine-readable status")
    status.add_argument("--logs", type=int, default=0, help="Show the last N audit log lines")
    status.set_defaults(func=command_status)

    prompt = sub.add_parser("prompt", help="Write the next Codex prompt to .research/next_prompt.md")
    add_research_dir_arg(prompt)
    prompt.add_argument("--output", help="Prompt output path")
    prompt.add_argument("--stdout", action="store_true", help="Print prompt content")
    prompt.add_argument("--copy", action="store_true", help="Copy prompt to clipboard when a clipboard tool exists")
    prompt.set_defaults(func=command_prompt)

    dashboard = sub.add_parser("dashboard", help="Generate a static HTML project dashboard")
    add_research_dir_arg(dashboard)
    dashboard.add_argument("--output", help="Dashboard output path")
    dashboard.add_argument("--open", action="store_true", help="Open dashboard in the default browser")
    dashboard.set_defaults(func=command_dashboard)

    run = sub.add_parser("run", help="Run one or more Codex autonomous cycles")
    add_research_dir_arg(run)
    run.add_argument("--task", help="Initial task if the research state does not exist")
    run.add_argument("--once", action="store_true", help="Run one cycle")
    run.add_argument("--cycles", type=int, help="Run a fixed number of cycles")
    run.add_argument("--until", help="Run until local time, e.g. '2026-05-15 10:00:00'")
    run.add_argument("--interval", type=int, default=1800, help="Seconds between cycles")
    run.add_argument("--codex-bin", default=os.environ.get("CODEX_BIN", "codex"), help="Codex CLI executable")
    run.add_argument("--dry-run", action="store_true", help="Only write the prompt; do not call Codex")
    run.set_defaults(func=command_run)

    advance = sub.add_parser("advance", help="Advance the current phase if the gate passes")
    add_research_dir_arg(advance)
    advance.add_argument("--force", action="store_true", help="Advance even if artifacts are missing")
    advance.set_defaults(func=command_advance)

    log = sub.add_parser("log", help="Append a structured audit log entry")
    add_research_dir_arg(log)
    log.add_argument("--action")
    log.add_argument("--rationale")
    log.add_argument("--outcome")
    log.add_argument("--blocker")
    log.add_argument("--next")
    log.set_defaults(func=command_log)

    memory = sub.add_parser("memory", help="Refresh the generated cross-phase memory bundle")
    add_research_dir_arg(memory)
    memory.add_argument("--json", action="store_true", help="Emit machine-readable refresh summary")
    memory.set_defaults(func=command_memory)

    runtime = sub.add_parser("runtime", help="Refresh workflow, evidence, queue, control, and memory files")
    add_research_dir_arg(runtime)
    runtime.add_argument("--json", action="store_true", help="Emit machine-readable runtime summary")
    runtime.set_defaults(func=command_runtime)

    evidence_cmd = sub.add_parser("evidence", help="Refresh and show the evidence registry")
    add_research_dir_arg(evidence_cmd)
    evidence_cmd.add_argument("--json", action="store_true", help="Emit the full evidence registry")
    evidence_cmd.set_defaults(func=command_evidence)

    queue_cmd = sub.add_parser("queue", help="Refresh and show the active task queue")
    add_research_dir_arg(queue_cmd)
    queue_cmd.add_argument("--json", action="store_true", help="Emit machine-readable queue summary")
    queue_cmd.set_defaults(func=command_queue)

    control_cmd = sub.add_parser("control", help="Show stop and success-condition decision")
    add_research_dir_arg(control_cmd)
    control_cmd.add_argument("--json", action="store_true", help="Emit machine-readable control decision")
    control_cmd.set_defaults(func=command_control)

    intervention = sub.add_parser("intervention", help="Record a structured human intervention patch")
    add_research_dir_arg(intervention)
    intervention.add_argument("--message", required=True, help="Human intervention text")
    intervention.add_argument("--kind", choices=sorted(researchctl.interventions.PATCH_KINDS), help="Optional patch kind")
    intervention.add_argument("--json", action="store_true", help="Emit the recorded patch")
    intervention.set_defaults(func=command_intervention)

    web = sub.add_parser("web", help="Start the interactive local Web UI")
    add_research_dir_arg(web)
    web.add_argument("--host", default="127.0.0.1", help="Bind host")
    web.add_argument("--port", type=int, default=8765, help="Bind port")
    web.add_argument("--open", action="store_true", help="Open in the default browser")
    web.set_defaults(func=command_web)

    validate = sub.add_parser("validate", help="Validate state and phase reports")
    add_research_dir_arg(validate)
    validate.set_defaults(func=command_validate)

    doctor = sub.add_parser("doctor", help="Check local PaperFactory dependencies")
    doctor.set_defaults(func=command_doctor)

    bib = sub.add_parser("bib", help="Run the BibTeX search helper through this launcher")
    bib.add_argument("tool_args", nargs=argparse.REMAINDER)
    bib.set_defaults(func=lambda args: command_delegate("bib_query.py", args.tool_args))

    check = sub.add_parser("check", help="Run manuscript hygiene checks through this launcher")
    check.add_argument("tool_args", nargs=argparse.REMAINDER)
    check.set_defaults(func=lambda args: command_delegate("manuscript_check.py", args.tool_args))

    plot = sub.add_parser("plot", help="Run the metric plotting helper through this launcher")
    plot.add_argument("tool_args", nargs=argparse.REMAINDER)
    plot.set_defaults(func=lambda args: command_delegate("make_metric_plot.py", args.tool_args))

    refs = sub.add_parser("fetch-refs", help="Download curated best-paper reference PDFs/source bundles")
    refs.add_argument("tool_args", nargs=argparse.REMAINDER)
    refs.set_defaults(func=lambda args: command_delegate("fetch_best_paper_references.py", args.tool_args))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
