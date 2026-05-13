# Artifact Contract

The controller advances phases only when required artifacts exist and the phase report marks the gate complete.

Each report lives at `.research/reports/<phase>.json`:

```json
{
  "phase": "scope",
  "status": "complete",
  "summary": "What was completed",
  "evidence": ["relative/path/to/artifact"],
  "risks": ["Known limitations"],
  "next": "Next concrete action",
  "cleanup": {
    "removed": ["relative/path/to/temp-file"],
    "archived": ["archive/cleanup/scope/old-scratch.md"],
    "kept": ["relative/path/to/raw-output"],
    "notes": "Raw outputs and required artifacts were preserved."
  },
  "route": {
    "decision": "advance",
    "target_phase": "",
    "reason": "Why this route is scientifically safe",
    "confidence": 0.8
  }
}
```

Allowed `status` values:

- `complete`: gate satisfied, controller may advance.
- `needs_more_work`: continue the same phase.
- `blocked`: cannot continue without an external dependency or user decision.
- `failed`: phase attempt failed and needs diagnosis.

Optional route decisions:

- `advance`: move to the next configured phase.
- `repeat`: keep the same phase active for another attempt.
- `jump_back`: return to a valid earlier phase named by `target_phase`.
- `skip_next`: skip only the immediately following phase.
- `jump_to`: jump to a valid configured phase or `complete`.

The base workflow is locked. `.research/workflow.json` stores only user-inserted custom phases, each with a prompt and default artifacts under `.research/custom/` plus `.research/reports/<custom_phase>.json`.

The controller also generates a cross-phase memory bundle under `.research/memory/` whenever a prompt is generated, a project is initialized, a phase advances, or `paperfactory memory` is run:

| File | Purpose |
| --- | --- |
| `memory/handoff.md` | Human-readable entry point for the next Codex cycle: current gate, recent outcomes, route history, risks, important artifacts, and claim/evidence notes. |
| `memory/phase_summaries.jsonl` | Compact JSONL records distilled from phase reports. |
| `memory/artifact_index.json` | Deterministic index of active `.research/` artifacts, excluding logs, progress feeds, archives, and memory files. |
| `memory/decision_memory.json` | Controller route history and report route decisions. |
| `memory/risk_memory.json` | Risks and non-complete report statuses that should not be lost across phases. |
| `memory/claim_memory.json` | Pointers and excerpts from claim/evidence files such as `paper/claim_evidence_map.md`, `results/main_results.md`, and `method/atomic_concepts.md`. |
| `memory/global_memory.md` | Stable task and phase facts for the whole research run. |
| `memory/phase_memory.md` | Active phase objective, gate, status, and missing artifacts. |
| `memory/negative_memory.json` | Failed, blocked, rejected, or risky paths Codex should not accidentally revive. |
| `memory/writing_memory.json` | Writing-stage view of claim/evidence and paper files. |

These files are generated from durable artifacts. Do not edit them as the source of truth; update the phase report, result artifact, or paper file that feeds them.

The long-running workflow also maintains operational control files:

| File | Purpose |
| --- | --- |
| `workflow_state.json` | Explicit state-machine view for each phase: `entry_condition`, `exit_gate`, `failure_policy`, `allowed_routes`, `retry_budget`, `max_runtime_hours`, `required_memory_inputs`, and `review_gate`. |
| `evidence/registry.json` | Claim-centered evidence flow with supporting artifacts, commands, metric sources, figure/table sources, confidence, and `paper_safe`. |
| `queue/tasks.jsonl` | Persistent task queue with `pending`, `running`, `done`, `failed`, `blocked`, and retry metadata. |
| `interventions/patches.jsonl` | Structured human intervention patches for scope, workflow, memory, and stop-condition changes. |
| `control/stop_conditions.json` | Stop and success conditions for unattended runs. |

Every phase should run an internal loop before setting `status: complete`: execute, self-check, repair, evidence-check, write the report, and choose the route. Record that loop in `report.self_check`.

Every phase should finish with a cleanup pass. Remove only obvious temporary files, caches, duplicate drafts, empty files, and obsolete scratch outputs created by that phase. When a file may have evidence or reproducibility value, move it to `.research/archive/cleanup/<phase>/` instead of deleting it, and record the reason in the phase report `cleanup` object.

Core artifact rules:

- Use real experiment scripts and raw outputs for metrics.
- Keep proxy experiments clearly labeled as proxy.
- Save failed runs and negative results.
- Do not overwrite raw outputs when summarizing.
- Do not delete raw outputs, source data, configs, logs, references, or files required to reproduce a result during cleanup.
- Store paper claims only after the supporting artifact exists.
- Pair every paper figure with `.research/figures/figure_plan.md`, source data, plotting script, and `.research/figures/source_data_manifest.json`.
- Pair every structural Draw.io diagram with `.drawio`, `.spec.yaml`, `.arch.json`, and `.svg`; track these in `.research/figures/drawio_bundle_manifest.json`.
- Keep late-stage paper writing issue-driven: `.research/paper/writing_issues.csv` should track section tasks, dependencies, citation verification, evidence status, and result placeholder state.
- Choose a conference page-budget mode before drafting full prose; record it in `.research/paper/page_budget.md` and map content to main text vs appendix.
- Use curated award-paper references during method/evidence/writing planning when helpful; record structural patterns in `.research/method/best_paper_experiment_notes.md` or `.research/paper/best_paper_style_notes.md`.
- Produce `.research/paper/main.tex` and `.research/paper/ref.bib` during `paper_drafting`; record citation, style, source, and compile checks in `.research/paper/latex_qa.md` during `internal_review`.
- Record final KLC-style source/PDF submission hygiene in `.research/paper/format_self_check.md` during `internal_review`.
- Mark result-backed claims as `planned`, `placeholder`, or `verified`; only verified evidence can support factual numerical claims.
