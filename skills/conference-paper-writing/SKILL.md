---
name: conference-paper-writing
description: Write or revise ML/AI conference papers from completed research evidence, especially ICLR/NeurIPS/ICML/AAAI-style submissions, with standardized claims, tables, figures, reproducibility statements, limitations, and appendices without overclaiming.
---

# Conference Paper Writing

Use this skill during `paper_evidence`, `paper_drafting`, and `internal_review` phases of the autonomous research workflow.

## Core Rule

Write from claims to evidence. Every main-text claim must point to a table, figure, theorem, experiment report, or clearly named appendix artifact. Prose interprets results; it does not serialize long metric strings.

## Main-Text Policy

- Lead with the strongest defensible claim and the table or figure that supports it.
- Put main method, strongest baselines, and headline ablations in main tables.
- Move pilot variants, failed gates, logs, hyperparameters, artifact paths, and large diagnostic grids to the appendix.
- Use cautious verbs such as `mitigates`, `improves`, `supports`, or `is diagnostic` when evidence is bounded.
- Reserve `SOTA`, `solves`, and broad superiority claims for broad, fair, protocol-matched comparisons.
- In abstracts and introductions, include at most one compact headline number per contribution.
- Do not repeat triples like `HR/NDCG/MRR = a/b/c` in paragraphs. Use tables.

## Tables

Every result table must state:

- dataset and processed split;
- candidate set or evaluation unit;
- metric cutoff and metric definition;
- seed count or statistical procedure;
- whether the row is final, diagnostic, proxy, or failed/negative.

Preferred table shapes:

- Main comparison: `Method`, `Signal/Modality`, `Protocol`, `Metric 1`, `Metric 2`, `Metric 3`, `Notes`.
- Ablation: `Variant`, `Removed/Changed Component`, `Primary Metric`, `Delta`, `Interpretation`.
- Negative result: `Attempt`, `Intended Fix`, `Observed Result`, `Decision`.
- Fairness matrix: `Baseline`, `Code`, `Checkpoint`, `Data`, `Protocol Match`, `Cost`, `Risk`.

Bold only the best supported main result per metric. Do not bold diagnostic or non-comparable rows.

## Figures

- Use figures for mechanisms, trends, tradeoffs, and failure boundaries.
- Do not make a chart when a compact table communicates the evidence better.
- Captions should state the takeaway and protocol, not only the plotted variables.
- Keep failure-boundary figures honest: show the limitation and the improvement together.
- Pair every figure with source data under `.research/figures/source_data/` or a documented experiment output path.

## Paper Structure

For a methods-oriented ML/AI paper:

1. Abstract: problem, gap, method, one bounded result, reproducibility note if relevant.
2. Introduction: motivation, why existing methods fall short, contribution list with evidence anchors.
3. Related Work: synthesize by mechanism and limitation, not paper-by-paper summary.
4. Method: define inputs, outputs, objective, algorithm, and inference path.
5. Experimental Setup: datasets, splits, metrics, baselines, implementation, compute.
6. Results: main comparison first, then ablations, robustness, and failure cases.
7. Limitations: known boundaries and what evidence does not establish.
8. Reproducibility/Ethics: code/data availability, seeds, compute, LLM usage disclosure when relevant.

## Reproducibility And Ethics

Include:

- dataset/source and processed split names;
- exact candidate construction, negative sampling, or benchmark protocol;
- checkpoint/model names and versions;
- hyperparameters and training/inference budgets;
- random seeds and statistical tests when claiming significance;
- hardware and environment notes for expensive experiments;
- LLM usage disclosure when LLMs materially contributed to ideation, writing, or evaluation.

## Autonomous Workflow Integration

When drafting from `.research/`:

1. Read `.research/results/main_results.md`, `.research/results/ablations.md`, `.research/results/failure_cases.md`, and `.research/figures/figure_plan.md`.
2. Build a claim-to-evidence map before writing prose.
3. If any intended claim lacks evidence, either move it to future work or write a blocker in `.research/reports/paper_drafting.json`.
4. Keep paper drafts in `.research/paper/` and appendices in `.research/paper/appendix.md`.

## Source Pointers

- ICLR author guides and templates.
- NeurIPS checklist conventions.
- ACL/ACM/IEEE formatting rules when those venues are targeted.
