# Codex PaperFactory

Codex PaperFactory is a Codex plugin for multi-day scientific and engineering research projects. It turns an initial research task into a recoverable workflow for literature survey, baselines, experiments, scientific figures, conference-paper drafting, and internal review.

It adapts the original `claude-codex` pipeline idea - durable task state, explicit gates, independent review, and recoverable artifacts - from software code review to autonomous research and paper production.

## What It Does

1. Start from one initial research task.
2. Create `.research/` as the durable project state.
3. Advance through explicit phases: scope, survey, data sanity, cheap baselines, method design, smoke tests, advanced comparisons, evidence consolidation, paper drafting, and internal review.
4. Use companion skills for scientific figures and conference-paper writing.
5. Require logs and artifacts at every phase.
6. Draft the paper only after the evidence gates are satisfied.

## Install

Clone this repository:

```bash
git clone git@github.com:happystander/codex-PaperFactory.git
```

The repository root is the plugin root. The Codex plugin manifest is:

```text
.codex-plugin/plugin.json
```

If your Codex setup uses a local marketplace file, use `codex-marketplace.json` or copy the entry from `codex-marketplace-entry.json` into your writable marketplace.

## Quick Start

From your target research project directory, initialize a research state:

```bash
python /path/to/codex-PaperFactory/scripts/researchctl.py init \
  --task "Develop a publishable method for ..."

python /path/to/codex-PaperFactory/scripts/researchctl.py next-prompt
```

Then ask Codex to use the `autonomous-research` skill with the generated prompt.

For unattended multi-cycle work:

```bash
bash /path/to/codex-PaperFactory/scripts/autonomous_loop.sh \
  --task "Develop a publishable method for ..." \
  --until "2026-05-15 10:00:00" \
  --interval 1800
```

The loop calls `codex exec --full-auto --skip-git-repo-check` once per interval with a phase-specific prompt generated from `.research/state.json`.

## Workflow Phases

The controller advances only when required artifacts exist and the phase report is complete:

1. `scope`: research target, exclusions, venue/domain, datasets, metrics, compute, success criteria.
2. `survey`: primary-source papers, official repos, datasets, leaderboards, baseline matrix, novelty gap.
3. `data_sanity`: dataset cards, split checks, leakage risks, evaluation protocol.
4. `cheap_baselines`: simple but strong baselines under the exact target protocol.
5. `method_design`: gap-driven method, staged escalation, falsifying ablations.
6. `method_smoke`: minimal method implementation and smoke-test evidence.
7. `advanced_comparison`: fair comparison to strong baselines or released checkpoints.
8. `paper_evidence`: main results, ablations, failure cases, figure plan, source-data manifest.
9. `paper_drafting`: paper and appendix written only from completed evidence.
10. `internal_review`: reviewer-style check for novelty, evidence, fairness, and reproducibility.

## Daily Commands

Check state:

```bash
python /path/to/codex-PaperFactory/scripts/researchctl.py status
```

Generate the next Codex prompt:

```bash
python /path/to/codex-PaperFactory/scripts/researchctl.py next-prompt
```

Advance only when the current phase gate is satisfied:

```bash
python /path/to/codex-PaperFactory/scripts/researchctl.py advance
```

Validate reports and state:

```bash
python /path/to/codex-PaperFactory/scripts/researchctl.py validate
```

Chinese usage notes are in `docs/usage.zh.md`.

## Included Skills

- `autonomous-research`: long-horizon research state machine and operating loop.
- `scientific-figure`: paper-ready figure contracts, source-data manifests, matplotlib style rules, captions, and export QA.
- `conference-paper-writing`: conference-style paper drafting from evidence, table policy, limitations, reproducibility, and internal review checks.

## Plotting Utility

Generate a quick paper-style metric figure from CSV or JSON:

```bash
python /path/to/codex-PaperFactory/scripts/make_metric_plot.py \
  --input metrics.csv \
  --x method \
  --y score \
  --output .research/figures/fig_main_metric \
  --formats svg,pdf
```

The plotting helper exports editable SVG/PDF and uses `.research/figures/source_data_manifest.json` as the traceability target in the workflow.

## Safety And Evidence Rules

- Do not invent citations, metrics, tables, figures, or experiment outcomes.
- Mark proxy, smoke, and diagnostic comparisons explicitly.
- Do not draft a paper before `paper_evidence` is complete.
- Every paper figure needs source data, plotting script, caption logic, and manifest entry.
- If protocols differ, mark the comparison diagnostic rather than final.

## Attribution

This plugin is derived from the workflow structure of:

- Author: Z-M-Huang
- Project: Claude Codex
- Repository: https://github.com/Z-M-Huang/claude-codex

The upstream repository license includes GPL-3.0 terms with an attribution requirement.
