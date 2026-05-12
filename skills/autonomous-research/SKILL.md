---
name: autonomous-research
description: Run or resume a long-horizon autonomous research project from an initial task, using durable logs, phase gates, experiments, baselines, and paper artifacts before drafting claims.
---

# Autonomous Research

Use this skill when the user wants Codex to conduct scientific or engineering research over many cycles with minimal human intervention.

## Core Rule

Research is a long-running project. Every meaningful action must leave an audit trail in `.research/logs/research.log`: timestamp, action, rationale, outcome, blocker if any, and next step.

Use `.research/` as the durable project state. If it does not exist, initialize it with:

```bash
python <PLUGIN_ROOT>/scripts/researchctl.py init --task "<initial research task>"
```

If the plugin root is unknown, locate this repository's `.codex-plugin/plugin.json`, then use the repository root as `<PLUGIN_ROOT>`.

## Operating Loop

For each work cycle:

1. Read `.research/state.json`, `.research/logs/research.log`, and `.research/results/summary.md` if present.
2. Run:

   ```bash
   python <PLUGIN_ROOT>/scripts/researchctl.py status
   python <PLUGIN_ROOT>/scripts/researchctl.py next-prompt
   ```

3. Perform only the current phase's work unless a blocker requires earlier-phase repair.
4. Save all phase artifacts under the paths named by `next-prompt`.
5. Write `.research/reports/<phase>.json` with `status: "complete"` only when the phase gate is genuinely satisfied. Use `status: "blocked"` or `status: "needs_more_work"` otherwise.
6. Run:

   ```bash
   python <PLUGIN_ROOT>/scripts/researchctl.py advance
   ```

7. If `advance` does not move the phase, continue the same phase in the next cycle.

## Phase Gates

The default pipeline is:

- `scope`: precise target, exclusions, venue/domain, datasets, metrics, compute assumptions, success criteria.
- `survey`: recent papers, official code, datasets, leaderboards, baseline matrix, novelty gap; use `paper-reader` and `citation-workflow` when useful.
- `data_sanity`: real dataset or explicitly marked proxy, split checks, leakage risks, metric protocol.
- `cheap_baselines`: simple but strong baselines under the exact target protocol.
- `method_design`: gap-driven method with falsifiable ablations and staged escalation plan.
- `method_smoke`: minimal method implementation and smoke test, with failure diagnosis.
- `advanced_comparison`: released checkpoints or fair reproduction of strong baselines when justified.
- `paper_evidence`: main results, ablations, robustness, failure cases, statistics, compute details, and paper-ready figure/source-data plans.
- `paper_drafting`: paper, appendix, and availability statements written from evidence only, using `conference-paper-writing`, `academic-polishing`, `citation-workflow`, and `data-availability`.
- `internal_review`: adversarial review of novelty, evidence, reproducibility, and overclaiming, using `manuscript-audit`.

Do not call a method novel until the nearest prior work, exact technical difference, falsifying ablation, and stronger-baseline relevance have been written down.

## Autonomy Policy

Default to continuing without asking the user. Make conservative assumptions and record them. Stop only for:

- missing credentials or unavailable paid/private data;
- destructive or high-cost actions not previously authorized;
- safety, legal, privacy, or ethics blockers;
- a scientific blocker where every reasonable next action would risk fabricating evidence.

## Evidence Policy

- Prefer primary sources: papers, official repositories, dataset pages, leaderboards, and model cards.
- If a fact may have changed recently, verify it before using it in the research plan or paper.
- Released checkpoints should be evaluated directly when possible. Retrain only when needed for protocol compatibility or when training is part of the claim.
- If any comparison differs in split, candidate set, negative sampling, metric, prompt budget, modalities, or inference constraints, mark it diagnostic rather than final.
- Never invent metrics, citations, tables, or experiment outcomes.

## Long Unattended Runs

For multi-day operation, use the loop script from the research project directory:

```bash
bash <PLUGIN_ROOT>/scripts/autonomous_loop.sh \
  --task "<initial research task>" \
  --until "YYYY-MM-DD HH:MM:SS" \
  --interval 1800
```

This script repeatedly asks `researchctl.py` for the next phase prompt and runs `codex exec --full-auto --skip-git-repo-check`.

## Paper Rule

Draft the paper only after `paper_evidence` is complete. Every main-text claim must point to a table, figure, experiment report, theorem, or appendix artifact. If evidence is bounded, use cautious wording such as "diagnostic", "suggests", "improves under this protocol", or "mitigates".

## Companion Skills

Use these plugin-local skills when their phases are reached:

- `scientific-figure`: during `paper_evidence`, plan publication figures, source-data manifests, captions, and optional matplotlib scripts.
- `conference-paper-writing`: during `paper_drafting` and `internal_review`, convert evidence into conference-style claims, tables, limitations, reproducibility notes, and appendix material.
- `paper-reader`: during `survey`, build source-grounded reading notes and baseline facts.
- `citation-workflow`: during `survey`, `paper_evidence`, and `paper_drafting`, map claims to citation support.
- `data-availability`: during `paper_evidence` and `paper_drafting`, prepare source-data/code/model availability.
- `academic-polishing`: during `paper_drafting`, improve prose without changing claims.
- `latex-typst-paper`: during manuscript source checks, preserve labels, math, citations, and build hygiene.
- `manuscript-audit`: during `internal_review`, run reviewer-style gate checks.
- `reviewer-response`: after reviews arrive, draft point-by-point response packages.
- `presentation-deck`: after evidence or draft completion, prepare talk/storyboard/PPT-ready material.
