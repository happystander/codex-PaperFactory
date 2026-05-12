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
  "next": "Next concrete action"
}
```

Allowed `status` values:

- `complete`: gate satisfied, controller may advance.
- `needs_more_work`: continue the same phase.
- `blocked`: cannot continue without an external dependency or user decision.
- `failed`: phase attempt failed and needs diagnosis.

Core artifact rules:

- Use real experiment scripts and raw outputs for metrics.
- Keep proxy experiments clearly labeled as proxy.
- Save failed runs and negative results.
- Do not overwrite raw outputs when summarizing.
- Store paper claims only after the supporting artifact exists.
- Pair every paper figure with `.research/figures/figure_plan.md`, source data, plotting script, and `.research/figures/source_data_manifest.json`.
- Keep late-stage paper writing issue-driven: `.research/paper/writing_issues.csv` should track section tasks, dependencies, citation verification, evidence status, and result placeholder state.
- Produce `.research/paper/main.tex` and `.research/paper/ref.bib` during `paper_drafting`; record citation, style, source, and compile checks in `.research/paper/latex_qa.md` during `internal_review`.
- Mark result-backed claims as `planned`, `placeholder`, or `verified`; only verified evidence can support factual numerical claims.
