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
/path/to/codex-PaperFactory/paperfactory new \
  --task "Develop a publishable method for ..."

/path/to/codex-PaperFactory/paperfactory prompt
```

Then ask Codex to use the `autonomous-research` skill with the generated prompt.

For a readable terminal panel and local HTML dashboard:

```bash
/path/to/codex-PaperFactory/paperfactory status --logs 8
/path/to/codex-PaperFactory/paperfactory dashboard --open
/path/to/codex-PaperFactory/paperfactory web --open
```

For unattended multi-cycle work:

```bash
/path/to/codex-PaperFactory/paperfactory run \
  --task "Develop a publishable method for ..." \
  --until "2026-05-15 10:00:00" \
  --interval 1800
```

The runner calls `codex exec --full-auto --skip-git-repo-check` once per interval with a phase-specific prompt generated from `.research/state.json`.

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
/path/to/codex-PaperFactory/paperfactory status
```

Generate the next Codex prompt:

```bash
/path/to/codex-PaperFactory/paperfactory prompt --copy
```

Advance only when the current phase gate is satisfied:

```bash
/path/to/codex-PaperFactory/paperfactory advance
```

Validate reports and state:

```bash
/path/to/codex-PaperFactory/paperfactory validate
```

Check local dependencies and generate the project UI:

```bash
/path/to/codex-PaperFactory/paperfactory doctor
/path/to/codex-PaperFactory/paperfactory dashboard --open
/path/to/codex-PaperFactory/paperfactory web --open
```

Chinese usage notes are in `docs/usage.zh.md`; launcher and dashboard details are in `docs/local-ui.md`.

## Interactive Web UI

Start a local control console:

```bash
/path/to/codex-PaperFactory/paperfactory web --open
```

The Web UI runs on localhost and supports:

- start/pause autonomous Codex cycles;
- detached background runs that keep going after the browser or Web UI is closed;
- Chinese agent-style stream view for visible Codex CLI output, tool logs, and system records;
- human intervention messages saved to `.research/human_interventions.md` and injected into the next prompt;
- editing the initial task stored in `.research/task.md` and `.research/state.json`;
- browsing `.research/` artifacts and previewing text files;
- viewing generated figures under `.research/figures/`;
- generating or running a top-conference-style review prompt through `manuscript-audit`.

Human intervention notes are applied on the next cycle. If an active `codex exec` process is already running, pause and restart when the note must take effect immediately.

## Included Skills

- `autonomous-research`: long-horizon research state machine and operating loop.
- `paper-reader`: source-grounded paper reading notes, baseline facts, figure/table anchors.
- `citation-workflow`: BibTeX/Zotero-exported library search, claim-to-citation support maps, LaTeX/Typst citation snippets.
- `scientific-figure`: paper-ready figure contracts, source-data manifests, matplotlib style rules, captions, and export QA.
- `conference-paper-writing`: conference-style paper drafting from evidence, table policy, limitations, reproducibility, and internal review checks.
- `latex-typst-paper`: source-aware checks for LaTeX/Typst manuscripts, bibliography, figures, tables, pseudocode, labels, and venue formatting.
- `academic-polishing`: claim-safe English/Chinese academic polishing, translation, title/abstract cleanup, and de-AI passes.
- `data-availability`: data/code/model availability statements, FAIR metadata, repository plans, and source-data packages.
- `manuscript-audit`: reviewer-style audit, submission gate, issue bundle, and revision roadmap.
- `reviewer-response`: point-by-point response letters, response trackers, and manuscript change checklists.
- `presentation-deck`: paper-sharing, lab meeting, conference talk, and PPT-ready storyboard generation.

## Plotting Utility

Generate a quick paper-style metric figure from CSV or JSON:

```bash
/path/to/codex-PaperFactory/paperfactory plot -- \
  --input metrics.csv \
  --x method \
  --y score \
  --output .research/figures/fig_main_metric \
  --formats svg,pdf
```

The plotting helper exports editable SVG/PDF and uses `.research/figures/source_data_manifest.json` as the traceability target in the workflow.

## Citation Utility

Search a local BibTeX or Zotero-exported library without extra dependencies:

```bash
/path/to/codex-PaperFactory/paperfactory bib -- \
  --bib references.bib \
  --query "vision language recommendation" \
  --year-min 2022 \
  --has doi \
  --limit 10
```

## Manuscript Hygiene Utility

Run a lightweight mechanical check before deeper review:

```bash
/path/to/codex-PaperFactory/paperfactory check -- paper/paper_draft.md --format markdown
/path/to/codex-PaperFactory/paperfactory check -- main.tex --format latex
/path/to/codex-PaperFactory/paperfactory check -- main.typ --format typst
```

## Safety And Evidence Rules

- Do not invent citations, metrics, tables, figures, or experiment outcomes.
- Mark proxy, smoke, and diagnostic comparisons explicitly.
- Do not draft a paper before `paper_evidence` is complete.
- Every paper figure needs source data, plotting script, caption logic, and manifest entry.
- Every citation should map to a specific claim and support grade.
- If protocols differ, mark the comparison diagnostic rather than final.

## Attribution

This plugin is derived from the workflow structure of:

- Author: Z-M-Huang
- Project: Claude Codex
- Repository: https://github.com/Z-M-Huang/claude-codex

The upstream repository license includes GPL-3.0 terms with an attribution requirement.
