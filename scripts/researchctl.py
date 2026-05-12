#!/usr/bin/env python3
"""State controller for the Codex PaperFactory plugin.

The controller is deliberately simple: it owns durable state, artifact
contracts, logs, and phase advancement. Codex still performs the scientific
work, but every cycle is recoverable from files under .research/.
"""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


STATE_VERSION = 1
DEFAULT_RESEARCH_DIR = ".research"
COMPLETE_STATUSES = {"complete", "completed", "pass", "passed"}
NON_ADVANCING_STATUSES = {"needs_more_work", "blocked", "failed", "error"}


@dataclass(frozen=True)
class Phase:
    key: str
    title: str
    objective: str
    required: tuple[str, ...]
    gate: str
    prompt_focus: tuple[str, ...]


PHASES: tuple[Phase, ...] = (
    Phase(
        key="scope",
        title="Research Scope",
        objective="Turn the initial task into a precise research target with bounded claims.",
        required=("scope/research_scope.md", "reports/scope.json"),
        gate="Scope names the target problem, exclusions, venue/domain, datasets, metrics, compute budget, risks, and success criteria.",
        prompt_focus=(
            "Define the exact research question and excluded scope.",
            "Write target datasets, metrics, venue/domain expectations, and success criteria.",
            "Record assumptions that allow autonomous progress without user intervention.",
        ),
    ),
    Phase(
        key="survey",
        title="Literature And Baseline Survey",
        objective="Build a primary-source survey and identify the closest reproducible baselines.",
        required=(
            "literature/reading_list.md",
            "literature/baseline_matrix.md",
            "literature/novelty_gap.md",
            "reports/survey.json",
        ),
        gate="Survey covers recent papers, official repositories, datasets, leaderboards, checkpoint availability, protocol details, reproduction cost, and fairness risks.",
        prompt_focus=(
            "Search broadly using primary sources and verify recent or unstable facts.",
            "Record conceptual SOTA separately from reproducible SOTA.",
            "State the nearest prior work and the precise unsolved gap.",
        ),
    ),
    Phase(
        key="data_sanity",
        title="Data Sanity",
        objective="Verify the real dataset or explicitly mark a proxy before experiments.",
        required=("data/data_card.md", "data/protocol.md", "reports/data_sanity.json"),
        gate="Data card records formats, counts, splits, labels, leakage checks, candidate construction, negative sampling, and metric protocol.",
        prompt_focus=(
            "Load or inspect the real dataset when available.",
            "Write exact split and metric protocol.",
            "Flag proxy data clearly and do not let it redefine the research target.",
        ),
    ),
    Phase(
        key="cheap_baselines",
        title="Cheap Baselines",
        objective="Run simple strong baselines before expensive method work.",
        required=(
            "baselines/cheap_baselines.md",
            "experiments/cheap_baselines/metrics.json",
            "reports/cheap_baselines.json",
        ),
        gate="At least one cheap but meaningful baseline is run under the exact target protocol, with commands and raw metrics saved.",
        prompt_focus=(
            "Implement or run simple baselines such as popularity, nearest neighbor, retrieval, heuristic, or frozen-model scoring.",
            "Use the same split, candidate set, metrics, and inference constraints planned for the method.",
            "Write metrics to experiments/cheap_baselines/metrics.json.",
        ),
    ),
    Phase(
        key="method_design",
        title="Method Design",
        objective="Design a staged method only after the gap and baseline floor are known.",
        required=("method/method_design.md", "experiments/method_smoke/plan.md", "reports/method_design.json"),
        gate="Method design states the new signal/objective/architecture/inference change, why it should help, and what ablation can falsify it.",
        prompt_focus=(
            "Compare against the nearest prior work before naming the contribution.",
            "Design a lightweight first version and a clear escalation path.",
            "Specify ablations and failure criteria before running expensive experiments.",
        ),
    ),
    Phase(
        key="method_smoke",
        title="Method Smoke Test",
        objective="Run the minimal method path and diagnose whether there is a promising signal.",
        required=(
            "experiments/method_smoke/result.md",
            "experiments/method_smoke/metrics.json",
            "reports/method_smoke.json",
        ),
        gate="Smoke test executes the method path on real or explicitly marked proxy data and compares against the strongest cheap baseline.",
        prompt_focus=(
            "Implement the smallest method path that tests the central hypothesis.",
            "Run a small experiment with saved command, config, outputs, and metrics.",
            "If it fails, preserve the failure and propose a concrete repair rather than hiding it.",
        ),
    ),
    Phase(
        key="advanced_comparison",
        title="Advanced Comparison",
        objective="Compare to strong baselines fairly once the method has a signal.",
        required=(
            "baselines/advanced_comparison.md",
            "experiments/advanced_comparison/metrics.json",
            "reports/advanced_comparison.json",
        ),
        gate="Advanced comparison uses released checkpoints or justified reproduction with matched protocol, or clearly records why escalation is not yet justified.",
        prompt_focus=(
            "Prefer released checkpoints and official evaluation code when possible.",
            "Retrain only when checkpoints are unavailable or protocol-incompatible.",
            "Mark any non-identical comparison as diagnostic instead of final.",
        ),
    ),
    Phase(
        key="paper_evidence",
        title="Paper Evidence",
        objective="Assemble paper-ready evidence without overclaiming.",
        required=(
            "figures/figure_plan.md",
            "figures/source_data_manifest.json",
            "results/main_results.md",
            "results/ablations.md",
            "results/failure_cases.md",
            "reports/paper_evidence.json",
        ),
        gate="Evidence includes main results, ablations, robustness or failure cases, statistics or multi-seed checks when appropriate, and reproducibility notes.",
        prompt_focus=(
            "Turn raw metrics into tables with protocol details.",
            "Use the scientific-figure skill to plan paper figures and source-data traceability.",
            "Add ablations that test the claimed mechanism.",
            "Include negative results and boundaries that matter for honest claims.",
        ),
    ),
    Phase(
        key="paper_drafting",
        title="Paper Drafting",
        objective="Draft a paper and appendix from existing evidence only.",
        required=("paper/paper_draft.md", "paper/appendix.md", "reports/paper_drafting.json"),
        gate="Draft cites artifact-backed evidence for each main claim and includes limitations and reproducibility details.",
        prompt_focus=(
            "Use the conference-paper-writing skill to build a claim-to-evidence map before prose.",
            "Write from claims to evidence: every main claim needs a table, figure, theorem, or appendix artifact.",
            "Use cautious language for bounded or diagnostic evidence.",
            "Do not invent citations, results, or unavailable baselines.",
        ),
    ),
    Phase(
        key="internal_review",
        title="Internal Review",
        objective="Adversarially review novelty, evidence, fairness, reproducibility, and paper quality.",
        required=("reviews/internal_review.md", "paper/camera_ready_checklist.md", "reports/internal_review.json"),
        gate="Review identifies blocking gaps, overclaims, missing baselines, reproducibility holes, and required revisions; completion means no blocking issues remain or they are explicitly scoped out.",
        prompt_focus=(
            "Review as a skeptical program committee member.",
            "Check whether a stronger baseline would invalidate the main claim.",
            "If blockers remain, set report status to needs_more_work and route back manually in the summary.",
        ),
    ),
)

PHASE_BY_KEY = {phase.key: phase for phase in PHASES}


def now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def research_dir_arg(value: str) -> Path:
    return Path(value).expanduser()


def resolve_research_dir(args: argparse.Namespace) -> Path:
    return research_dir_arg(args.research_dir).resolve()


def state_path(root: Path) -> Path:
    return root / "state.json"


def log_path(root: Path) -> Path:
    return root / "logs" / "research.log"


def summary_path(root: Path) -> Path:
    return root / "results" / "summary.md"


def ensure_dirs(root: Path) -> None:
    for rel in (
        "logs",
        "scope",
        "literature",
        "baselines",
        "data",
        "method",
        "experiments",
        "figures",
        "results",
        "paper",
        "reviews",
        "reports",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def append_log(root: Path, message: str) -> None:
    append_text(log_path(root), f"[{now()}] {message.rstrip()}\n")


def load_state(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.exists():
        raise SystemExit(f"Research state not found: {path}. Run init first.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state JSON at {path}: {exc}") from exc


def write_state(root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = iso_now()
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rel_exists_nonempty(root: Path, rel: str) -> bool:
    path = root / rel
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def current_phase(state: dict[str, Any]) -> Phase | None:
    key = state.get("phase")
    if key == "complete":
        return None
    if key not in PHASE_BY_KEY:
        raise SystemExit(f"Unknown phase in state.json: {key!r}")
    return PHASE_BY_KEY[str(key)]


def phase_index(key: str) -> int:
    for index, phase in enumerate(PHASES):
        if phase.key == key:
            return index
    raise KeyError(key)


def report_for(root: Path, phase: Phase) -> dict[str, Any] | None:
    return read_json(root / "reports" / f"{phase.key}.json")


def report_status(root: Path, phase: Phase) -> str | None:
    report = report_for(root, phase)
    status = report.get("status") if report else None
    return str(status) if status is not None else None


def missing_required(root: Path, phase: Phase) -> list[str]:
    return [rel for rel in phase.required if not rel_exists_nonempty(root, rel)]


def can_advance(root: Path, phase: Phase) -> tuple[bool, list[str], str | None]:
    missing = missing_required(root, phase)
    status = report_status(root, phase)
    if missing:
        return False, missing, status
    if status is None:
        return False, [f"reports/{phase.key}.json: missing status"], status
    normalized = status.strip().lower()
    if normalized in COMPLETE_STATUSES:
        return True, [], status
    if normalized in NON_ADVANCING_STATUSES:
        return False, [f"reports/{phase.key}.json status is {status!r}"], status
    return False, [f"reports/{phase.key}.json status {status!r} is not an advancing status"], status


def command_init(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args)
    if state_path(root).exists() and not args.force:
        raise SystemExit(f"{state_path(root)} already exists. Use --force to reinitialize.")

    ensure_dirs(root)
    task = args.task.strip()
    if not task:
        raise SystemExit("--task must not be empty")

    (root / "task.md").write_text(f"# Initial Research Task\n\n{task}\n", encoding="utf-8")
    summary_path(root).write_text("# Research Summary\n\n", encoding="utf-8")
    state = {
        "schema_version": STATE_VERSION,
        "task": task,
        "created_at": iso_now(),
        "updated_at": iso_now(),
        "phase": PHASES[0].key,
        "phase_history": [],
        "cycles": [],
        "controller": str(Path(__file__).resolve()),
    }
    write_state(root, state)
    append_log(root, f"Action: initialized research project at {root}")
    append_log(root, f"Rationale: initial task = {task}")
    append_log(root, f"Next: complete phase {PHASES[0].key} and write required artifacts.")
    print(f"Initialized research project: {root}")
    print(f"Current phase: {PHASES[0].key}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args)
    state = load_state(root)
    phase = current_phase(state)
    print(f"Research dir: {root}")
    print(f"Task: {state.get('task', '')}")
    if phase is None:
        print("Phase: complete")
        return 0
    missing = missing_required(root, phase)
    status = report_status(root, phase)
    print(f"Phase: {phase.key} - {phase.title}")
    print(f"Objective: {phase.objective}")
    print(f"Report status: {status or 'missing'}")
    if missing:
        print("Missing artifacts:")
        for rel in missing:
            print(f"  - {rel}")
    else:
        print("Required artifacts: present")
    print(f"Gate: {phase.gate}")
    return 0


def shell_quote(path: Path) -> str:
    return shlex.quote(str(path))


def build_next_prompt(root: Path, state: dict[str, Any]) -> str:
    phase = current_phase(state)
    controller = Path(__file__).resolve()
    if phase is None:
        return (
            "The autonomous research project is marked complete. Read .research/reviews/internal_review.md "
            "and .research/paper/camera_ready_checklist.md, then report residual risks only."
        )

    missing = missing_required(root, phase)
    status = report_status(root, phase)
    required_list = "\n".join(f"- {rel}" for rel in phase.required)
    missing_list = "\n".join(f"- {rel}" for rel in missing) if missing else "- none"
    focus_list = "\n".join(f"- {item}" for item in phase.prompt_focus)
    controller_cmd = f"python {shell_quote(controller)}"
    companion_skills = []
    if phase.key == "paper_evidence":
        companion_skills.append("scientific-figure")
    if phase.key in {"paper_drafting", "internal_review"}:
        companion_skills.append("conference-paper-writing")
    companion_text = (
        "\nCompanion skills to apply this phase:\n" + "\n".join(f"- {skill}" for skill in companion_skills)
        if companion_skills
        else ""
    )

    return f"""You are running the Codex PaperFactory long-horizon workflow.

Research directory: {root}
Initial task: {state.get("task", "")}
Current phase: {phase.key} - {phase.title}
Objective: {phase.objective}

Gate:
{phase.gate}

Required artifacts for this phase:
{required_list}

Currently missing or incomplete:
{missing_list}

Current phase report status: {status or "missing"}

Phase focus:
{focus_list}
{companion_text}

Operating rules:
- Read .research/state.json, .research/task.md, .research/logs/research.log, and .research/results/summary.md before acting.
- Append concise audit entries to .research/logs/research.log with action, rationale, outcome, blocker if any, and next step.
- Use primary sources for papers, repositories, datasets, benchmarks, and model cards. Verify recent or unstable facts before relying on them.
- Do not invent citations, metrics, tables, or experiment outcomes.
- Save raw outputs, commands, configs, metrics, and summaries under .research/ or clearly referenced project experiment directories.
- Write .research/reports/{phase.key}.json. Set status to "complete" only if the gate is genuinely satisfied; otherwise use "needs_more_work" or "blocked".
- Finish the cycle by running: {controller_cmd} --research-dir {shell_quote(root)} advance
"""


def command_next_prompt(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args)
    state = load_state(root)
    print(build_next_prompt(root, state))
    return 0


def command_advance(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args)
    state = load_state(root)
    phase = current_phase(state)
    if phase is None:
        print("Already complete.")
        return 0

    ok, problems, status = can_advance(root, phase)
    if not ok and not args.force:
        append_log(root, f"Outcome: phase {phase.key} not advanced; problems={problems}")
        print(f"Phase {phase.key} cannot advance.")
        for problem in problems:
            print(f"- {problem}")
        return 1

    old_key = phase.key
    idx = phase_index(old_key)
    next_key = "complete" if idx + 1 >= len(PHASES) else PHASES[idx + 1].key
    state.setdefault("phase_history", []).append(
        {
            "phase": old_key,
            "completed_at": iso_now(),
            "report_status": status,
            "forced": bool(args.force),
        }
    )
    state["phase"] = next_key
    write_state(root, state)
    append_log(root, f"Outcome: advanced phase {old_key} -> {next_key}.")
    print(f"Advanced phase: {old_key} -> {next_key}")
    return 0


def command_log(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args)
    _ = load_state(root)
    parts = []
    if args.action:
        parts.append(f"Action: {args.action}")
    if args.rationale:
        parts.append(f"Rationale: {args.rationale}")
    if args.outcome:
        parts.append(f"Outcome: {args.outcome}")
    if args.blocker:
        parts.append(f"Blocker: {args.blocker}")
    if args.next:
        parts.append(f"Next: {args.next}")
    if not parts:
        raise SystemExit("Nothing to log. Provide at least one field.")
    append_log(root, " | ".join(parts))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args)
    state = load_state(root)
    errors = 0
    warnings = 0

    if state.get("schema_version") != STATE_VERSION:
        print(f"ERROR: unsupported schema_version {state.get('schema_version')}")
        errors += 1

    phase_key = state.get("phase")
    if phase_key != "complete" and phase_key not in PHASE_BY_KEY:
        print(f"ERROR: unknown phase {phase_key!r}")
        errors += 1

    for phase in PHASES:
        report = report_for(root, phase)
        if report is None:
            warnings += 1
            continue
        status = str(report.get("status", "")).lower()
        if status not in COMPLETE_STATUSES | NON_ADVANCING_STATUSES:
            print(f"ERROR: report {phase.key} has invalid status {status!r}")
            errors += 1
        if report.get("phase") not in (phase.key, None):
            print(f"ERROR: report {phase.key} phase field does not match")
            errors += 1

    print(f"Validation: {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Codex PaperFactory state.")
    parser.add_argument("--research-dir", default=DEFAULT_RESEARCH_DIR, help="Research state directory")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize .research state")
    init.add_argument("--task", required=True, help="Initial research task")
    init.add_argument("--force", action="store_true", help="Overwrite existing state")
    init.set_defaults(func=command_init)

    status = sub.add_parser("status", help="Show current phase and gate status")
    status.set_defaults(func=command_status)

    next_prompt = sub.add_parser("next-prompt", help="Print the next Codex work prompt")
    next_prompt.set_defaults(func=command_next_prompt)

    advance = sub.add_parser("advance", help="Advance if current phase artifacts pass the gate")
    advance.add_argument("--force", action="store_true", help="Advance even if artifacts are missing")
    advance.set_defaults(func=command_advance)

    log = sub.add_parser("log", help="Append a structured audit entry")
    log.add_argument("--action")
    log.add_argument("--rationale")
    log.add_argument("--outcome")
    log.add_argument("--blocker")
    log.add_argument("--next")
    log.set_defaults(func=command_log)

    validate = sub.add_parser("validate", help="Validate controller state and reports")
    validate.set_defaults(func=command_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
