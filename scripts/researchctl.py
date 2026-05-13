#!/usr/bin/env python3
"""State controller for the Codex PaperFactory plugin.

The controller is deliberately simple: it owns durable state, artifact
contracts, logs, and phase advancement. Codex still performs the scientific
work, but every cycle is recoverable from files under .research/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


STATE_VERSION = 1
DEFAULT_RESEARCH_DIR = ".research"
WORKFLOW_CONFIG = "workflow.json"
COMPLETE_STATUSES = {"complete", "completed", "pass", "passed"}
NON_ADVANCING_STATUSES = {"needs_more_work", "blocked", "failed", "error"}
ROUTE_DECISIONS = {
    "advance",
    "repeat",
    "redo",
    "jump_back",
    "jump_to",
    "skip_next",
    "skip_to",
}
MEMORY_DIR = "memory"
MEMORY_ARTIFACT_LIMIT = 500
MEMORY_RECENT_PHASE_LIMIT = 12
MEMORY_SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "archive",
    "logs",
    "memory",
    "progress",
}
MEMORY_TEXT_EXTENSIONS = {
    ".bib",
    ".csv",
    ".json",
    ".md",
    ".tex",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class Phase:
    key: str
    title: str
    objective: str
    required: tuple[str, ...]
    gate: str
    prompt_focus: tuple[str, ...]
    kind: str = "base"
    custom_prompt: str = ""
    insert_after: str = ""


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
            "literature/reference_codebases.md",
            "literature/novelty_gap.md",
            "reports/survey.json",
        ),
        gate="Survey covers recent papers, official repositories, 5-8 inspected reference codebases, datasets, leaderboards, checkpoint availability, protocol details, reproduction cost, and fairness risks.",
        prompt_focus=(
            "Search broadly using primary sources and verify recent or unstable facts.",
            "Use paper-reader for source-grounded paper notes and citation-workflow for local bibliography/citation mapping.",
            "Run an AI-Researcher-style Prepare step: select 5-8 reference codebases by relevance, recency, reproducibility, readability, and implementation coverage.",
            "Write the reference codebase matrix with repository URL, paper link if any, license, install status, runnable entry points, reusable ideas, and reasons to exclude weak repos.",
            "Record conceptual SOTA separately from reproducible SOTA.",
            "State the nearest prior work and the precise unsolved gap.",
        ),
    ),
    Phase(
        key="data_sanity",
        title="Data Sanity",
        objective="Verify the real dataset or explicitly mark a proxy before experiments.",
        required=("data/data_card.md", "data/benchmark_profile.md", "data/protocol.md", "reports/data_sanity.json"),
        gate="Data card and benchmark profile record formats, counts, splits, labels, leakage checks, candidate construction, negative sampling, baseline/comparison/evaluation candidates, and metric protocol.",
        prompt_focus=(
            "Load or inspect the real dataset when available.",
            "Write a benchmark profile: dataset, baseline floor, comparison targets, evaluation metrics, and domain-specific constraints.",
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
        required=(
            "method/atomic_concepts.md",
            "method/method_design.md",
            "method/implementation_plan.md",
            "experiments/method_smoke/plan.md",
            "reports/method_design.json",
        ),
        gate="Method design decomposes the innovation into atomic concepts, states the new signal/objective/architecture/inference change, maps each concept to papers and implementation hooks, and names ablations that can falsify it.",
        prompt_focus=(
            "Compare against the nearest prior work before naming the contribution.",
            "Break the innovation into atomic academic definitions; for each record math, paper trace, code trace, implementation hook, and falsifying ablation.",
            "Write a concrete implementation plan covering data processing, model, training, testing, commands, expected outputs, and low-budget smoke settings.",
            "Do not directly import reference repositories into the final method; adapt the ideas into self-contained code with attribution notes.",
            "Design a lightweight first version and a clear escalation path.",
            "Specify ablations and failure criteria before running expensive experiments.",
        ),
    ),
    Phase(
        key="method_smoke",
        title="Method Smoke Test",
        objective="Run the minimal method path and diagnose whether there is a promising signal.",
        required=(
            "experiments/method_smoke/project_manifest.md",
            "experiments/method_smoke/result.md",
            "experiments/method_smoke/metrics.json",
            "reports/method_smoke.json",
        ),
        gate="Smoke test executes a self-contained minimal method path on real or explicitly marked proxy data, records the runnable project manifest, and compares against the strongest cheap baseline.",
        prompt_focus=(
            "Implement the smallest method path that tests the central hypothesis.",
            "When building method code, keep a clear data/model/training/testing/data_processing/run_training_testing.py-style structure unless the project already has a stronger established layout.",
            "Run a very small first experiment, such as a two-epoch or otherwise low-budget smoke run, before longer training.",
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
            "experiments/advanced_comparison/refinement_plan.md",
            "experiments/advanced_comparison/metrics.json",
            "reports/advanced_comparison.json",
        ),
        gate="Advanced comparison uses released checkpoints or justified reproduction with matched protocol, includes a judge/refinement pass against the atomic concepts and protocol, or clearly records why escalation is not yet justified.",
        prompt_focus=(
            "Run a judge/refinement pass before escalation: audit implementation against atomic concepts, protocol, and reference codebases, then save the repair or refinement plan.",
            "Prefer released checkpoints and official evaluation code when possible.",
            "Retrain only when checkpoints are unavailable or protocol-incompatible.",
            "After each advanced run, analyze why the result changed and whether the next experiment is justified.",
            "Mark any non-identical comparison as diagnostic instead of final.",
        ),
    ),
    Phase(
        key="paper_evidence",
        title="Paper Evidence",
        objective="Assemble paper-ready evidence without overclaiming.",
        required=(
            "figures/figure_plan.md",
            "figures/diagram_plan.md",
            "figures/source_data_manifest.json",
            "figures/drawio_bundle_manifest.json",
            "results/main_results.md",
            "results/ablations.md",
            "results/failure_cases.md",
            "results/experiment_analysis.md",
            "reports/paper_evidence.json",
        ),
        gate="Evidence includes main results, ablations, robustness or failure cases, experiment analysis, paper figures/diagrams with editable source bundles, statistics or multi-seed checks when appropriate, and reproducibility notes.",
        prompt_focus=(
            "Turn raw metrics into tables with protocol details.",
            "Use the scientific-figure skill to plan paper figures and source-data traceability.",
            "Use drawio-academic-skills for architecture, workflow, roadmap, ablation pipeline, and formula-safe diagrams; keep .drawio, .spec.yaml, .arch.json, and .svg bundles together under figures/.",
            "Write figures/diagram_plan.md and figures/drawio_bundle_manifest.json with each diagram's purpose, source bundle, export path, caption intent, and validation status.",
            "Write an experiment-analysis note that explains observed gains, failures, confounders, and justified follow-up experiments.",
            "Add ablations that test the claimed mechanism.",
            "Include negative results and boundaries that matter for honest claims.",
        ),
    ),
    Phase(
        key="paper_drafting",
        title="Paper Drafting",
        objective="Draft a paper and appendix from existing evidence only.",
        required=(
            "paper/claim_evidence_map.md",
            "paper/page_budget.md",
            "paper/writing_issues.csv",
            "paper/paper_draft.md",
            "paper/main.tex",
            "paper/ref.bib",
            "paper/appendix.md",
            "paper/availability.md",
            "reports/paper_drafting.json",
        ),
        gate="Draft cites artifact-backed evidence for each main claim and includes limitations and reproducibility details.",
        prompt_focus=(
            "Use the conference-paper-writing skill to build a claim-to-evidence map before prose.",
            "Use conference-page-budget before drafting main prose: choose 8p-double, 9p-single, or appendix mode; write paper/page_budget.md; map main-vs-appendix content.",
            "Use latex-paper-skills when available: paper-from-zero for routing, empirical-paper-writer for experimental papers, arxiv-paper-writer for review papers, results-backfill for verified result upgrades, and latex-rhythm-refiner after content stabilizes.",
            "Create an issues-style writing contract in paper/writing_issues.csv; track section tasks, dependencies, citation verification, evidence status, and placeholder/result status.",
            "Use citation-workflow for citation support checks, data-availability for availability wording, and academic-polishing for final language passes.",
            "Draft section-by-section with checkpoints: methodology, related work, experiments, introduction, conclusion, then abstract.",
            "Produce LaTeX source and BibTeX alongside the Markdown draft; compile or record why compilation is unavailable.",
            "Use templates/conference_papers/8p_double_column_main.tex, 9p_single_column_main.tex, or appendix.tex as the starting layout when no venue-specific template is supplied.",
            "Write from claims to evidence: every main claim needs a table, figure, theorem, or appendix artifact.",
            "Use cautious language for bounded or diagnostic evidence.",
            "Do not invent citations, results, or unavailable baselines.",
        ),
    ),
    Phase(
        key="internal_review",
        title="Internal Review",
        objective="Adversarially review novelty, evidence, fairness, reproducibility, and paper quality.",
        required=(
            "reviews/internal_review.md",
            "reviews/top_conference_review.md",
            "paper/latex_qa.md",
            "paper/format_self_check.md",
            "paper/camera_ready_checklist.md",
            "reports/internal_review.json",
        ),
        gate="Review identifies blocking gaps, overclaims, missing baselines, reproducibility holes, and required revisions; completion means no blocking issues remain or they are explicitly scoped out.",
        prompt_focus=(
            "Review as a skeptical program committee member.",
            "Audit every atomic concept against the implemented code, ablations, and paper claims.",
            "Use manuscript-audit as a top-conference reviewer after paper_drafting is complete, and write reviews/top_conference_review.md.",
            "Use latex-paper-skills QA where available: issue_workflow audit, citation_policy audit-bib/audit-tex, source_ranker, style_profile, compile_paper, and record results in paper/latex_qa.md.",
            "Use paper-format-self-check for KLC-style final source/PDF hygiene: quotes, i.e./e.g., BibTeX venue cleanup, published-version citations, nonbreaking references, figure/table readability, appendix navigation, list spacing, and cropping.",
            "Run latex-rhythm-refiner only after claim support, citations, and numbers are stable; preserve citation positions and verified numeric claims.",
            "Check whether a stronger baseline would invalidate the main claim.",
            "If blockers remain, set report status to needs_more_work and route back manually in the summary.",
        ),
    ),
)

PHASE_BY_KEY = {phase.key: phase for phase in PHASES}
START_SENTINEL = "__start__"
CUSTOM_PHASE_PREFIX = "custom_"
SAFE_KEY_PATTERN = re.compile(r"[^a-z0-9_]+")
CUSTOM_DEFAULT_GATE = (
    "Custom phase prompt has been addressed, a concise result note exists, and "
    "the custom phase report explains evidence, residual risks, and the next route."
)


def workflow_config_path(root: Path) -> Path:
    return root / WORKFLOW_CONFIG


def phase_config_dict(phase: Phase, *, enabled: bool = True) -> dict[str, Any]:
    return {
        "key": phase.key,
        "title": phase.title,
        "objective": phase.objective,
        "gate": phase.gate,
        "enabled": enabled,
        "kind": "base",
        "locked": True,
        "insert_after": "",
        "prompt": "",
    }


def custom_required_paths(key: str) -> tuple[str, ...]:
    return (f"custom/{key}.md", f"reports/{key}.json")


def slugify_key(value: str, fallback: str = "phase") -> str:
    slug = SAFE_KEY_PATTERN.sub("_", value.strip().lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        slug = fallback
    if not slug.startswith(CUSTOM_PHASE_PREFIX):
        slug = f"{CUSTOM_PHASE_PREFIX}{slug}"
    return slug[:80]


def unique_custom_key(raw_key: str, title: str, seen: set[str]) -> str:
    base = slugify_key(raw_key or title or "phase")
    key = base
    counter = 2
    while key in seen or key in PHASE_BY_KEY:
        suffix = f"_{counter}"
        key = f"{base[:80 - len(suffix)]}{suffix}"
        counter += 1
    return key


def valid_insert_after(value: str) -> str:
    key = str(value or "").strip()
    if key == START_SENTINEL:
        return key
    if key in PHASE_BY_KEY:
        return key
    return PHASES[-1].key


def custom_phase_config_dict(
    *,
    key: str,
    title: str,
    prompt: str,
    insert_after: str,
    enabled: bool = True,
    objective: str = "",
    gate: str = "",
) -> dict[str, Any]:
    title = title.strip() or key
    prompt = prompt.strip()
    objective = objective.strip() or "Run the inserted user-defined research step."
    gate = gate.strip() or CUSTOM_DEFAULT_GATE
    return {
        "key": key,
        "title": title[:120],
        "objective": objective[:500],
        "gate": gate[:700],
        "enabled": enabled,
        "kind": "custom",
        "locked": False,
        "insert_after": valid_insert_after(insert_after),
        "prompt": prompt[:8000],
        "required": list(custom_required_paths(key)),
    }


def read_custom_phase_config(root: Path) -> list[dict[str, Any]]:
    path = workflow_config_path(root)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, dict):
        return []
    raw_items: list[Any] = []
    if isinstance(raw.get("custom_phases"), list):
        raw_items = raw["custom_phases"]
    elif isinstance(raw.get("phases"), list):
        # Backward compatible read: old workflow files contained every base row.
        # Base rows are now immutable, so only unknown/custom rows are retained.
        raw_items = [
            item
            for item in raw["phases"]
            if isinstance(item, dict)
            and (item.get("kind") == "custom" or str(item.get("key") or "") not in PHASE_BY_KEY)
        ]

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("key") or "Custom Phase")
        key = unique_custom_key(str(item.get("key") or ""), title, seen)
        seen.add(key)
        rows.append(
            custom_phase_config_dict(
                key=key,
                title=title,
                prompt=str(item.get("prompt") or item.get("custom_prompt") or ""),
                insert_after=str(item.get("insert_after") or item.get("after") or PHASES[-1].key),
                enabled=bool(item.get("enabled", True)),
                objective=str(item.get("objective") or ""),
                gate=str(item.get("gate") or ""),
            )
        )
    return rows


def workflow_config_for_ui(root: Path) -> list[dict[str, Any]]:
    """Return the fixed base workflow with inserted custom phases."""
    custom_rows = read_custom_phase_config(root)
    by_anchor: dict[str, list[dict[str, Any]]] = {START_SENTINEL: []}
    for phase in PHASES:
        by_anchor[phase.key] = []
    for row in custom_rows:
        by_anchor.setdefault(valid_insert_after(str(row.get("insert_after") or "")), []).append(row)

    rows: list[dict[str, Any]] = []
    rows.extend(by_anchor.get(START_SENTINEL, []))
    for phase in PHASES:
        rows.append(phase_config_dict(phase))
        rows.extend(by_anchor.get(phase.key, []))
    return rows


def configured_phases(root: Path | None = None) -> tuple[Phase, ...]:
    if root is None:
        return PHASES
    phases: list[Phase] = []
    for item in workflow_config_for_ui(root):
        if not item.get("enabled", True):
            continue
        key = str(item["key"])
        if key in PHASE_BY_KEY:
            base = PHASE_BY_KEY[key]
            phases.append(base)
        else:
            prompt = str(item.get("prompt") or "").strip()
            raw_required = item.get("required")
            custom_required = (
                tuple(str(rel) for rel in raw_required if str(rel).strip())
                if isinstance(raw_required, list)
                else custom_required_paths(key)
            )
            phases.append(
                Phase(
                    key=key,
                    title=str(item.get("title") or key),
                    objective=str(item.get("objective") or "Run the inserted user-defined research step."),
                    required=custom_required or custom_required_paths(key),
                    gate=str(item.get("gate") or CUSTOM_DEFAULT_GATE),
                    prompt_focus=(prompt or "Follow the user-defined prompt for this inserted phase.",),
                    kind="custom",
                    custom_prompt=prompt,
                    insert_after=str(item.get("insert_after") or ""),
                )
            )
    return tuple(phases) or PHASES


def write_workflow_config(root: Path, phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    custom_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in phases:
        if not isinstance(item, dict):
            continue
        raw_key = str(item.get("key") or "")
        if raw_key in PHASE_BY_KEY and item.get("kind") != "custom":
            continue
        title = str(item.get("title") or raw_key or "Custom Phase")
        key = unique_custom_key(raw_key, title, seen)
        seen.add(key)
        custom_rows.append(
            custom_phase_config_dict(
                key=key,
                title=title,
                prompt=str(item.get("prompt") or ""),
                insert_after=str(item.get("insert_after") or item.get("after") or PHASES[-1].key),
                enabled=bool(item.get("enabled", True)),
                objective=str(item.get("objective") or ""),
                gate=str(item.get("gate") or ""),
            )
        )
    workflow_config_path(root).write_text(
        json.dumps({"schema_version": 2, "custom_phases": custom_rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return workflow_config_for_ui(root)


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
        MEMORY_DIR,
        "results",
        "paper",
        "reviews",
        "reports",
        "pages",
        "custom",
        "archive/cleanup",
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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def memory_path(root: Path, filename: str) -> Path:
    return root / MEMORY_DIR / filename


def compact_text(value: Any, limit: int = 1200) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def normalize_list(value: Any, *, limit: int = 30, text_limit: int = 500) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    else:
        items = [value]
    normalized: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        else:
            text = str(item)
        text = compact_text(text, text_limit)
        if text:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def normalize_route_decision(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = {"decision": raw}
    if not isinstance(raw, dict):
        return None
    decision = str(raw.get("decision") or raw.get("action") or "advance").strip().lower()
    if decision not in ROUTE_DECISIONS:
        return None
    return {
        "decision": "repeat" if decision == "redo" else decision,
        "target_phase": str(raw.get("target_phase") or raw.get("target") or "").strip(),
        "reason": compact_text(raw.get("reason") or "", 700),
        "confidence": raw.get("confidence"),
    }


def artifact_role(rel: Path) -> str:
    parts = rel.parts
    if not parts:
        return "artifact"
    top = parts[0]
    if rel.as_posix() in {"state.json", "task.md", WORKFLOW_CONFIG}:
        return "control"
    if top == "reports":
        return "phase_report"
    if top == "pages":
        return "phase_page"
    if top == "paper":
        return "paper"
    if top == "figures":
        return "figure"
    if top == "experiments":
        return "experiment"
    if top in {"scope", "literature", "baselines", "data", "method", "results", "reviews", "custom"}:
        return top
    return "artifact"


def phase_hint_for_artifact(rel: Path) -> str:
    parts = rel.parts
    if not parts:
        return ""
    top = parts[0]
    if top == "reports" and rel.suffix == ".json":
        return rel.stem
    if top == "pages" and rel.suffix == ".md":
        return rel.stem
    if top == "custom":
        return rel.stem
    if top == "scope":
        return "scope"
    if top == "literature":
        return "survey"
    if top == "data":
        return "data_sanity"
    if top == "method":
        return "method_design"
    if top == "results":
        return "paper_evidence"
    if top == "reviews":
        return "internal_review"
    if top == "paper":
        return "paper_drafting"
    if top == "figures":
        return "paper_evidence"
    if top == "experiments" and len(parts) > 1:
        if parts[1].startswith("cheap"):
            return "cheap_baselines"
        if parts[1].startswith("method"):
            return "method_smoke"
        if parts[1].startswith("advanced"):
            return "advanced_comparison"
    if top == "baselines" and len(parts) > 1 and "advanced" in parts[1]:
        return "advanced_comparison"
    if top == "baselines":
        return "cheap_baselines"
    return ""


def iter_memory_artifact_files(root: Path):
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        try:
            rel_dir = current.relative_to(root)
        except ValueError:
            continue
        if rel_dir.parts and rel_dir.parts[0] in MEMORY_SKIP_DIRS:
            dirnames[:] = []
            continue
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in MEMORY_SKIP_DIRS and not dirname.startswith(".")
        ]
        for filename in filenames:
            if filename.endswith((".tmp", ".lock", ".pyc", ".pyo")):
                continue
            path = current / filename
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if rel.parts and rel.parts[0] in MEMORY_SKIP_DIRS:
                continue
            yield path, rel


def build_artifact_index(root: Path, phase: Phase | None) -> dict[str, Any]:
    required = set(phase.required if phase else ())
    rows: list[dict[str, Any]] = []
    for path, rel in iter_memory_artifact_files(root) or []:
        try:
            stat = path.stat()
        except OSError:
            continue
        suffix = path.suffix.lower()
        rel_text = rel.as_posix()
        rows.append(
            {
                "path": rel_text,
                "role": artifact_role(rel),
                "phase_hint": phase_hint_for_artifact(rel),
                "bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                "extension": suffix,
                "text_like": suffix in MEMORY_TEXT_EXTENSIONS,
                "required_current_phase": rel_text in required,
            }
        )

    priority = {
        "control": 0,
        "phase_report": 1,
        "scope": 2,
        "literature": 3,
        "data": 4,
        "baselines": 5,
        "method": 6,
        "experiment": 7,
        "figure": 8,
        "results": 9,
        "paper": 10,
        "reviews": 11,
        "custom": 12,
        "phase_page": 13,
        "artifact": 20,
    }
    rows.sort(
        key=lambda row: (
            0 if row["required_current_phase"] else 1,
            priority.get(str(row["role"]), 20),
            str(row["path"]),
        )
    )
    limited = rows[:MEMORY_ARTIFACT_LIMIT]
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "current_phase": "complete" if phase is None else phase.key,
        "total_indexed": len(rows),
        "truncated": len(rows) > len(limited),
        "artifacts": limited,
    }


def collect_phase_report_records(root: Path) -> list[dict[str, Any]]:
    reports_dir = root / "reports"
    if not reports_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(reports_dir.glob("*.json")):
        report = read_json(path)
        if not isinstance(report, dict):
            continue
        phase_key = str(report.get("phase") or path.stem)
        route = normalize_route_decision(
            report.get("route") or report.get("routing") or report.get("phase_route")
        )
        records.append(
            {
                "phase": phase_key,
                "report": f"reports/{path.name}",
                "status": str(report.get("status") or "unknown"),
                "summary": compact_text(report.get("summary") or report.get("result") or "", 1200),
                "evidence": normalize_list(report.get("evidence"), limit=40, text_limit=500),
                "risks": normalize_list(report.get("risks") or report.get("risk"), limit=40, text_limit=500),
                "next": compact_text(report.get("next") or report.get("next_action") or "", 900),
                "cleanup": report.get("cleanup") if isinstance(report.get("cleanup"), dict) else {},
                "route": route,
            }
        )
    return records


def write_phase_summaries(root: Path, records: list[dict[str, Any]]) -> None:
    path = memory_path(root, "phase_summaries.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_text_excerpt(path: Path, limit: int = 1800) -> str:
    if path.suffix.lower() not in MEMORY_TEXT_EXTENSIONS:
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return text.strip()[:limit]


def build_decision_memory(root: Path, state: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    report_routes = []
    for record in records:
        route = record.get("route")
        if isinstance(route, dict):
            report_routes.append(
                {
                    "phase": record.get("phase"),
                    "report": record.get("report"),
                    **route,
                }
            )
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "current_phase": state.get("phase"),
        "phase_history": state.get("phase_history", [])[-50:],
        "controller_routes": state.get("phase_routes", [])[-50:],
        "report_routes": report_routes[-50:],
    }


def build_risk_memory(state: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    risks: list[dict[str, Any]] = []
    for record in records:
        for risk in record.get("risks", []):
            risks.append({"phase": record.get("phase"), "report": record.get("report"), "risk": risk})
        status = str(record.get("status") or "").lower()
        if status and status not in COMPLETE_STATUSES:
            risks.append(
                {
                    "phase": record.get("phase"),
                    "report": record.get("report"),
                    "risk": f"Report status is {status}; phase may need attention.",
                }
            )
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "current_phase": state.get("phase"),
        "open_risks": risks[-80:],
    }


def build_claim_memory(root: Path) -> dict[str, Any]:
    source_rels = (
        "paper/claim_evidence_map.md",
        "results/main_results.md",
        "results/ablations.md",
        "results/failure_cases.md",
        "results/experiment_analysis.md",
        "literature/novelty_gap.md",
        "method/atomic_concepts.md",
        "method/method_design.md",
    )
    sources: list[dict[str, str]] = []
    for rel in source_rels:
        path = root / rel
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size == 0:
            continue
        excerpt = read_text_excerpt(path)
        sources.append({"path": rel, "excerpt": excerpt})
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "sources": sources,
        "rule": "Only claims backed by explicit artifact evidence may be used as factual paper claims.",
    }


def build_handoff_markdown(
    root: Path,
    state: dict[str, Any],
    phase: Phase | None,
    records: list[dict[str, Any]],
    artifact_index: dict[str, Any],
    decision_memory: dict[str, Any],
    risk_memory: dict[str, Any],
    claim_memory: dict[str, Any],
) -> str:
    phase_key = "complete" if phase is None else phase.key
    phase_title = "Complete" if phase is None else phase.title
    missing = [] if phase is None else missing_required(root, phase)
    status = "complete" if phase is None else (report_status(root, phase) or "missing")
    lines = [
        "# Research Memory Handoff",
        "",
        f"- Updated: {iso_now()}",
        f"- Task: {state.get('task', '')}",
        f"- Current phase: `{phase_key}` - {phase_title}",
        f"- Current report status: {status}",
        "",
        "## Read Order",
        "",
        "1. `.research/memory/handoff.md`",
        "2. `.research/state.json` and `.research/task.md`",
        "3. `.research/memory/phase_summaries.jsonl`",
        "4. `.research/memory/decision_memory.json` and `.research/memory/risk_memory.json`",
        "5. `.research/memory/artifact_index.json`",
        "6. Current phase required artifacts and any human intervention notes",
        "",
        "## Active Gate",
        "",
    ]
    if phase is None:
        lines.append("The workflow is complete. Review final artifacts and residual risks only.")
    else:
        lines.extend(
            [
                phase.gate,
                "",
                "Required artifacts:",
            ]
        )
        missing_set = set(missing)
        for rel in phase.required:
            marker = "missing" if rel in missing_set else "present"
            lines.append(f"- `{rel}`: {marker}")
    lines.extend(["", "## Recent Phase Outcomes", ""])
    if records:
        for record in records[-MEMORY_RECENT_PHASE_LIMIT:]:
            summary = record.get("summary") or record.get("next") or "No summary recorded."
            lines.append(
                f"- `{record.get('phase')}` status `{record.get('status')}`: {compact_text(summary, 350)}"
            )
    else:
        lines.append("- No phase reports have been written yet.")

    lines.extend(["", "## Route And Decision Memory", ""])
    routes = list(decision_memory.get("controller_routes") or [])[-8:]
    report_routes = list(decision_memory.get("report_routes") or [])[-8:]
    if routes or report_routes:
        for route in routes:
            lines.append(
                f"- Controller route `{route.get('from_phase')}` -> `{route.get('resolved_next_phase')}`: "
                f"{route.get('decision')} ({compact_text(route.get('reason'), 220)})"
            )
        for route in report_routes:
            lines.append(
                f"- Report route `{route.get('phase')}`: {route.get('decision')} -> "
                f"{route.get('target_phase') or route.get('resolved_next_phase') or 'default'} "
                f"({compact_text(route.get('reason'), 220)})"
            )
    else:
        lines.append("- No route decisions recorded yet.")

    lines.extend(["", "## Open Risks", ""])
    open_risks = list(risk_memory.get("open_risks") or [])[-15:]
    if open_risks:
        for item in open_risks:
            lines.append(f"- `{item.get('phase')}`: {compact_text(item.get('risk'), 280)}")
    else:
        lines.append("- No open risks recorded in phase reports.")

    lines.extend(["", "## High-Value Artifacts", ""])
    artifact_rows = list(artifact_index.get("artifacts") or [])
    required_rows = [row for row in artifact_rows if row.get("required_current_phase")]
    other_rows = [row for row in artifact_rows if not row.get("required_current_phase")]
    selected = (required_rows + other_rows)[:25]
    if selected:
        for row in selected:
            required_label = " required" if row.get("required_current_phase") else ""
            lines.append(
                f"- `{row.get('path')}` ({row.get('role')}, {row.get('bytes')} bytes{required_label})"
            )
    else:
        lines.append("- No artifacts indexed yet.")

    lines.extend(["", "## Claim And Evidence Notes", ""])
    claim_sources = list(claim_memory.get("sources") or [])
    if claim_sources:
        for source in claim_sources:
            lines.append(f"- Review `{source.get('path')}` before making or revising paper claims.")
    else:
        lines.append("- No claim/evidence source files exist yet.")

    lines.extend(
        [
            "",
            "## Memory Contract",
            "",
            "- Treat this handoff as the cross-phase memory entry point; do not rely on chat history.",
            "- If new evidence changes direction, update the relevant artifact and phase report rather than only writing a log.",
            "- Keep `results/summary.md` concise and cumulative; detailed evidence belongs in phase artifacts.",
        ]
    )
    return "\n".join(lines) + "\n"


def refresh_memory(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    ensure_dirs(root)
    phase = current_phase(state, root)
    records = collect_phase_report_records(root)
    artifact_index = build_artifact_index(root, phase)
    decision_memory = build_decision_memory(root, state, records)
    risk_memory = build_risk_memory(state, records)
    claim_memory = build_claim_memory(root)

    write_json(memory_path(root, "artifact_index.json"), artifact_index)
    write_phase_summaries(root, records)
    write_json(memory_path(root, "decision_memory.json"), decision_memory)
    write_json(memory_path(root, "risk_memory.json"), risk_memory)
    write_json(memory_path(root, "claim_memory.json"), claim_memory)
    memory_path(root, "handoff.md").write_text(
        build_handoff_markdown(
            root,
            state,
            phase,
            records,
            artifact_index,
            decision_memory,
            risk_memory,
            claim_memory,
        ),
        encoding="utf-8",
    )
    return {
        "memory_dir": str(root / MEMORY_DIR),
        "current_phase": "complete" if phase is None else phase.key,
        "reports": len(records),
        "artifacts": int(artifact_index.get("total_indexed") or 0),
        "claim_sources": len(claim_memory.get("sources") or []),
    }


def current_phase(state: dict[str, Any], root: Path | None = None) -> Phase | None:
    key = state.get("phase")
    if key == "complete":
        return None
    for phase in configured_phases(root):
        if phase.key == key:
            return phase
    if key in PHASE_BY_KEY:
        return PHASE_BY_KEY[str(key)]
    if key not in PHASE_BY_KEY:
        raise SystemExit(f"Unknown phase in state.json: {key!r}")
    return PHASE_BY_KEY[str(key)]


def phase_index(key: str, root: Path | None = None) -> int:
    for index, phase in enumerate(configured_phases(root)):
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


def default_next_phase_key(phases: tuple[Phase, ...], old_key: str) -> str:
    phase_keys = [item.key for item in phases]
    if old_key in phase_keys:
        idx = phase_keys.index(old_key)
        return "complete" if idx + 1 >= len(phases) else phases[idx + 1].key
    return phases[0].key if phases else "complete"


def route_decision_for(root: Path, phase: Phase) -> dict[str, Any] | None:
    report = report_for(root, phase)
    if not report:
        return None
    raw = report.get("route") or report.get("routing") or report.get("phase_route")
    return normalize_route_decision(raw)


def resolve_route(root: Path, phases: tuple[Phase, ...], old_key: str) -> tuple[str, dict[str, Any] | None]:
    phase_keys = [item.key for item in phases]
    default_next = default_next_phase_key(phases, old_key)
    phase = next((item for item in phases if item.key == old_key), None)
    route = route_decision_for(root, phase) if phase else None
    if not route:
        return default_next, None

    decision = str(route["decision"])
    next_key = default_next
    if decision == "repeat":
        next_key = old_key
    elif decision == "skip_next":
        if old_key in phase_keys:
            idx = phase_keys.index(old_key)
            next_key = "complete" if idx + 2 >= len(phases) else phases[idx + 2].key
    elif decision in {"jump_back", "jump_to", "skip_to"}:
        target = str(route.get("target_phase") or "")
        if target in phase_keys or target == "complete":
            next_key = target
        else:
            route = {**route, "ignored": True, "ignore_reason": f"unknown target_phase {target!r}"}
            next_key = default_next
    elif decision == "advance":
        next_key = default_next

    return next_key, {**route, "from_phase": old_key, "resolved_next_phase": next_key}


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
    refresh_memory(root, state)
    print(f"Initialized research project: {root}")
    print(f"Current phase: {PHASES[0].key}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args)
    state = load_state(root)
    phase = current_phase(state, root)
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
    phase = current_phase(state, root)
    refresh_memory(root, state)
    controller = Path(__file__).resolve()
    tools_doc = controller.parents[1] / "docs" / "open-research-tooling.md"
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
    if phase.key in {"survey", "data_sanity", "method_design", "method_smoke", "advanced_comparison"}:
        companion_skills.append("auto-research")
    if phase.key in {"method_design", "paper_evidence", "paper_drafting", "internal_review"}:
        companion_skills.append("best-paper-writing-reference")
    if phase.key == "survey":
        companion_skills.extend(["paper-reader", "citation-workflow"])
    if phase.key == "paper_evidence":
        companion_skills.extend(["scientific-figure", "drawio-academic-skills", "citation-workflow", "data-availability"])
    if phase.key in {"paper_drafting", "internal_review"}:
        companion_skills.extend(["conference-paper-writing", "conference-page-budget"])
    if phase.key == "paper_drafting":
        companion_skills.extend(
            [
                "paper-from-zero",
                "empirical-paper-writer",
                "arxiv-paper-writer",
                "results-backfill",
                "latex-rhythm-refiner",
                "academic-polishing",
                "latex-typst-paper",
                "paper-format-self-check",
                "citation-workflow",
                "data-availability",
            ]
        )
    if phase.key == "internal_review":
        companion_skills.extend(
            [
                "manuscript-audit",
                "paper-format-self-check",
                "latex-rhythm-refiner",
                "arxiv-paper-writer",
                "empirical-paper-writer",
                "latex-typst-paper",
                "data-availability",
            ]
        )
    companion_text = (
        "\nCompanion skills to apply this phase:\n" + "\n".join(f"- {skill}" for skill in companion_skills)
        if companion_skills
        else ""
    )
    open_tool_guidance_by_phase = {
        "survey": (
            "Use OpenAlex, Crossref, arXiv, and Semantic Scholar APIs when useful for source discovery, DOI/arXiv metadata, citation trails, and related-work expansion.",
            "Cache raw API responses under .research/literature/api_cache/ and cite the exact query, date, and source.",
            "For PDFs, prefer GROBID for structured TEI extraction when available; otherwise use pdftotext or Python PDF packages and record the extraction method.",
        ),
        "data_sanity": (
            "Use DVC or git-lfs for large data/model artifacts when available; otherwise write a manifest with checksums, source URLs, and access constraints.",
            "Use Hydra/OmegaConf-style config files or a small equivalent config format so dataset, split, and metric choices are reproducible.",
        ),
        "cheap_baselines": (
            "Track baseline parameters, commands, metrics, and output artifacts with MLflow when available, or save the same fields in JSON/CSV under .research/experiments/.",
            "Prefer Makefile or Snakemake targets for rerunnable baseline commands when the experiment has more than one step.",
        ),
        "method_smoke": (
            "Use MLflow for smoke-run parameters, metrics, checkpoints, and notes when available.",
            "Use Hydra/OmegaConf-style configs and a Makefile or Snakemake target for the smallest rerunnable method path.",
        ),
        "advanced_comparison": (
            "Use MLflow to compare runs and checkpoint metadata when available; keep released-checkpoint provenance and evaluation commands explicit.",
            "Use DVC/git-lfs or checksummed manifests for large checkpoints and result artifacts.",
            "Use Snakemake or Makefile targets for multi-step fair-comparison pipelines.",
            "When designing final comparison evidence, inspect the curated award-paper references for baseline tiers, ablation structure, and failure-boundary reporting.",
        ),
        "paper_evidence": (
            "Use the local plotting helper plus scientific-figure/drawio skills for figures; preserve raw figure source data and exact plotting commands.",
            "Keep every table and figure backed by a source JSON/CSV/Markdown manifest so claims are traceable.",
            "Compare figure/table roles against docs/best-paper-writing-references.md and write reusable patterns to .research/paper/best_paper_style_notes.md.",
        ),
        "paper_drafting": (
            "Compile with latexmk, pdflatex, biber, bibtex, tectonic, or pandoc when available; save build commands and failure logs in paper/latex_qa.md.",
            "Use Crossref/arXiv/OpenAlex metadata checks for uncertain bibliography entries rather than inventing fields.",
            "Use curated award-paper references for structure and page-budget decisions; summarize patterns, do not copy text.",
        ),
        "internal_review": (
            "Re-run available LaTeX/BibTeX build tools and citation metadata checks before final review.",
            "Audit whether experiment tracking, data versioning, and workflow commands are sufficient for another researcher to reproduce the claims.",
            "Compare the draft against curated award-paper standards for experiment coverage, limitations, appendix strategy, and figure/table readability.",
        ),
    }
    open_tool_guidance = open_tool_guidance_by_phase.get(
        phase.key,
        (
            "Use available open-source research tools when they improve evidence quality, reproducibility, or paper build reliability.",
            "If a recommended tool is unavailable, record the fallback and why it is sufficient for this phase.",
        ),
    )
    open_tool_text = (
        "\nOpen-source research tooling to prefer when available:\n"
        f"- Tooling guide: {tools_doc}\n"
        + "\n".join(f"- {item}" for item in open_tool_guidance)
    )
    custom_phase_text = ""
    if phase.kind == "custom":
        custom_phase_text = (
            "\nThis is a user-inserted custom phase. Follow this phase prompt exactly unless it conflicts "
            "with evidence safety or the fixed PaperFactory research gates:\n"
            f"{phase.custom_prompt or phase.prompt_focus[0]}\n"
            "\nWrite the custom phase result note to the required custom artifact path, then write the "
            f"phase report at .research/reports/{phase.key}.json.\n"
        )
    memory_config_path = root / "memory_config.json"
    if memory_config_path.exists():
        try:
            memory_config = json.loads(memory_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            memory_config = {}
    else:
        memory_config = {}
    memory_defaults = {
        "summary": True,
        "logs": True,
        "human_interventions": True,
        "artifact_index": True,
    }
    memory = {key: bool(memory_config.get(key, default)) for key, default in memory_defaults.items()}
    intervention_path = root / "human_interventions.md"
    if memory["human_interventions"] and intervention_path.exists():
        intervention_text = intervention_path.read_text(encoding="utf-8", errors="ignore")[-4000:].strip()
    else:
        intervention_text = ""
    intervention_section = (
        "\nHuman intervention notes to honor in the next cycle:\n"
        f"{intervention_text}\n"
        "\nIf a note conflicts with older logs or plans, follow the newest human intervention and record the change.\n"
        if intervention_text
        else ""
    )
    memory_reads = [".research/state.json", ".research/task.md"]
    memory_reads.append(".research/memory/handoff.md")
    if memory["summary"]:
        memory_reads.append(".research/results/summary.md")
        memory_reads.append(".research/memory/phase_summaries.jsonl")
    if memory["logs"]:
        memory_reads.append(".research/logs/research.log")
        memory_reads.append(".research/memory/decision_memory.json")
        memory_reads.append(".research/memory/risk_memory.json")
    if memory["human_interventions"]:
        memory_reads.append(".research/human_interventions.md when present")
    if memory["artifact_index"]:
        memory_reads.append(".research/memory/artifact_index.json")
        memory_reads.append(".research/memory/claim_memory.json")
        memory_reads.append("the current phase required artifact files when present")
    memory_list = "\n".join(f"- {item}" for item in memory_reads)
    progress_feed = root / "progress" / "feed.jsonl"

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

User-visible progress feed:
- Append concise natural-language progress updates to: {progress_feed}
- Use one valid JSON object per line. Schema:
  {{"ts":"<ISO time>","role":"agent","phase":"{phase.key}","status":"working|blocked|done|note","message":"<1-3 user-facing sentences about what you did or are doing>","files":["<artifact path>", "..."]}}
- Write a progress event when you start the cycle, after each meaningful artifact or experiment action, when blocked, and before finishing.
- The message must be natural language for the human user. Do not dump raw logs, stack traces, or tool output into this feed.
- Maintain a concise user-facing phase page at .research/pages/{phase.key}.md. Update it after meaningful work with: what changed, evidence produced, decisions made, blockers, and next action. This page is for the UI, so write it in natural language and link artifact paths.

Phase focus:
{focus_list}
{companion_text}
{open_tool_text}
{custom_phase_text}
{intervention_section}

Operating rules:
- Before acting, read the selected memory sources:
{memory_list}
- Treat .research/memory/handoff.md as the first cross-phase memory entry point. It is generated by the controller from phase reports, artifact state, route decisions, risks, and claim/evidence files.
- Do not rely on chat history for cross-phase continuity. If a decision, risk, result, or paper claim matters later, persist it in the relevant artifact and phase report so the memory bundle can carry it forward.
- Before relying on an external research tool, check whether it is available with ./paperfactory doctor, command -v, or a small import test. Prefer installed tools; do not block the phase only because an optional tool is missing.
- The base PaperFactory workflow is fixed. Treat user-inserted custom phases as extra checkpoints, not as permission to weaken required evidence gates.
- Append concise audit entries to .research/logs/research.log with action, rationale, outcome, blocker if any, and next step.
- Use primary sources for papers, repositories, datasets, benchmarks, and model cards. Verify recent or unstable facts before relying on them.
- Do not invent citations, metrics, tables, or experiment outcomes.
- Save raw outputs, commands, configs, metrics, and summaries under .research/ or clearly referenced project experiment directories.
- Before finishing this phase, run a cleanup pass. Remove only obvious temporary files, caches, duplicate drafts, empty files, and obsolete scratch outputs created by this phase. Never delete required artifacts, raw experiment outputs, source data, citations, configs, logs, or files needed to reproduce a result.
- If a file may have evidence value but should leave the active folder, move it to .research/archive/cleanup/{phase.key}/ with a short reason instead of deleting it.
- Record cleanup in .research/reports/{phase.key}.json under "cleanup": {{"removed":["..."],"archived":["..."],"kept":["..."],"notes":"..."}}. Use empty lists when nothing needed cleanup.
- Write .research/reports/{phase.key}.json. Set status to "complete" only if the gate is genuinely satisfied; otherwise use "needs_more_work" or "blocked".
- In that report, include a self-check route object:
  {{"decision":"advance|repeat|jump_back|skip_next|jump_to","target_phase":"<phase key or complete when needed>","reason":"<why this route is scientifically safer>","confidence":0.0}}
- Use "repeat" when this phase should be redone, "jump_back" when an earlier fixed or custom phase must be revisited, "skip_next" only when the next phase is genuinely unnecessary, and "jump_to" only when you can name a valid target phase.
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
    phase = current_phase(state, root)
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
    phases = configured_phases(root)
    next_key, route = resolve_route(root, phases, old_key)
    state.setdefault("phase_history", []).append(
        {
            "phase": old_key,
            "completed_at": iso_now(),
            "report_status": status,
            "forced": bool(args.force),
            "next_phase": next_key,
            "route": route,
        }
    )
    if route:
        state.setdefault("phase_routes", []).append({**route, "decided_at": iso_now()})
    state["phase"] = next_key
    write_state(root, state)
    route_note = f" route={route}" if route else ""
    append_log(root, f"Outcome: advanced phase {old_key} -> {next_key}.{route_note}")
    refresh_memory(root, state)
    print(f"Advanced phase: {old_key} -> {next_key}")
    if route:
        print(f"Route decision: {route.get('decision')} {route.get('reason') or ''}".rstrip())
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


def command_memory(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args)
    state = load_state(root)
    payload = refresh_memory(root, state)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Refreshed memory bundle: {root / MEMORY_DIR}")
        print(f"Current phase: {payload['current_phase']}")
        print(f"Phase reports: {payload['reports']}")
        print(f"Indexed artifacts: {payload['artifacts']}")
        print(f"Claim/evidence sources: {payload['claim_sources']}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    root = resolve_research_dir(args)
    state = load_state(root)
    errors = 0
    warnings = 0

    if state.get("schema_version") != STATE_VERSION:
        print(f"ERROR: unsupported schema_version {state.get('schema_version')}")
        errors += 1

    phases = configured_phases(root)
    phase_keys = {phase.key for phase in phases}
    phase_key = state.get("phase")
    if phase_key != "complete" and phase_key not in phase_keys and phase_key not in PHASE_BY_KEY:
        print(f"ERROR: unknown phase {phase_key!r}")
        errors += 1

    for phase in phases:
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

    memory = sub.add_parser("memory", help="Refresh the generated cross-phase memory bundle")
    memory.add_argument("--json", action="store_true", help="Emit machine-readable refresh summary")
    memory.set_defaults(func=command_memory)

    validate = sub.add_parser("validate", help="Validate controller state and reports")
    validate.set_defaults(func=command_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
