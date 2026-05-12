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
- Produce `.research/paper/main.tex` and `.research/paper/ref.bib` during `paper_drafting`; record citation, style, source, and compile checks in `.research/paper/latex_qa.md` during `internal_review`.
- Mark result-backed claims as `planned`, `placeholder`, or `verified`; only verified evidence can support factual numerical claims.
