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
- `survey`: recent papers, official code, paper priority scoring, structured claim extraction, datasets, leaderboards, baseline matrix, code interface map, novelty gap; use `research-library-workflow`, `paper-reader`, `citation-workflow`, and `llm-rl-toolkit` for LLM/Agent/RAG/RL tasks when useful.
- `data_sanity`: real dataset or explicitly marked proxy, split checks, leakage risks, metric protocol; use `scientific-runtime-tooling` when datasets depend on scientific software, simulation inputs, or domain reference databases.
- `cheap_baselines`: baseline code probe under the exact target protocol; inspect reference implementations, run minimal checks, record diagnostic/reference metrics, and decide which baselines need later full reproduction. The key is legacy and does not require the baseline to be cheap.
- `method_design`: gap-driven method with nearest-prior module diff, candidate idea generation, critic rejection pass, novelty risk score, falsifiable ablations, and staged escalation plan.
- `method_smoke`: minimal method implementation and smoke test, with failure diagnosis, runtime provenance when scientific tools are involved, and diagnostic comparison against baseline-probe/reference metrics.
- `advanced_comparison`: released checkpoints or fair reproduction of strong baselines after the method shows a credible signal; scientific-runtime comparisons need official-doc/toolref provenance and protocol-matched validation.
- `paper_evidence`: main results, ablations, robustness, failure cases, statistics, compute details, and paper-ready figure/source-data plans.
- `paper_drafting`: paper, appendix, and availability statements written from evidence only, using `conference-paper-writing`, `academic-polishing`, `citation-workflow`, and `data-availability`.
- `internal_review`: adversarial review of novelty, evidence, reproducibility, and overclaiming, using `manuscript-audit`.

Do not call a method novel until the nearest three prior works, exact module-level technical differences, falsifying ablations, stronger-baseline relevance, and novelty risk score have been written down.

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
- `conference-page-budget`: during `paper_drafting`, choose 8-page double-column, 9-page single-column, or appendix layout and allocate section/page budget.
- `best-paper-writing-reference`: during `method_design`, `paper_evidence`, and `paper_drafting`, compare experiment and writing plans against curated award-paper structures.
- `paper-reader`: during `survey`, build source-grounded reading notes and baseline facts.
- `research-library-workflow`: during `survey`, `paper_evidence`, `paper_drafting`, and `internal_review`, use structured literature workspaces, ScholarAIO/Zotero/EndNote-style ingestion, topic/citation graph checks, and citation validation.
- `llm-rl-toolkit`: during LLM/Agent/RAG/RL `survey`, `method_design`, `method_smoke`, and `advanced_comparison`, choose Open-LLM resources and mature TRL/verl/ms-swift/LLaMA-Factory/OpenRLHF-style frameworks before custom infrastructure.
- `scientific-runtime-tooling`: during `data_sanity`, `cheap_baselines`, `method_design`, `method_smoke`, `advanced_comparison`, and scientific `paper_evidence`, use official docs or local tool references, record runtime provenance, and avoid guessing domain parameters.
- `citation-workflow`: during `survey`, `paper_evidence`, and `paper_drafting`, map claims to citation support.
- `data-availability`: during `paper_evidence` and `paper_drafting`, prepare source-data/code/model availability.
- `academic-polishing`: during `paper_drafting`, improve prose without changing claims.
- `latex-typst-paper`: during manuscript source checks, preserve labels, math, citations, and build hygiene.
- `paper-format-self-check`: during late `paper_drafting` and `internal_review`, run KLC-style source/PDF submission hygiene checks.
- `manuscript-audit`: during `internal_review`, run reviewer-style gate checks.
- `reviewer-response`: after reviews arrive, draft point-by-point response packages.
- `presentation-deck`: after evidence or draft completion, prepare talk/storyboard/PPT-ready material.
