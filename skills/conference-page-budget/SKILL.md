---
name: conference-page-budget
description: Plan, draft, and audit ML/AI conference papers under strict page budgets, especially 8-page double-column submissions, 9-page single-column ICLR/OpenReview-style submissions, and appendix/supplement layouts. Use for section budgeting, template selection, page-pressure triage, appendix migration, and camera-ready structure.
---

# Conference Page Budget

Use this skill during `paper_drafting`, `internal_review`, or venue retargeting when a paper must fit a strict conference format.

## Core Rule

Page budget is an argument budget. Allocate space to claims, evidence, and reviewer concerns before writing prose. Do not shrink fonts, abuse `\resizebox`, or hide required experimental details to fit pages.

## Modes

| Mode | Use When | Template |
| --- | --- | --- |
| `8p-double` | NeurIPS/ICML/ACL/AAAI-like compact double-column main paper | `templates/conference_papers/8p_double_column_main.tex` |
| `9p-single` | ICLR/OpenReview-like single-column main paper | `templates/conference_papers/9p_single_column_main.tex` |
| `appendix` | Supplementary material, proofs, extra experiments, details | `templates/conference_papers/appendix.tex` |

## 8-Page Double-Column Budget

Target main-text allocation, excluding references unless venue says otherwise:

| Section | Page Budget | Purpose |
| --- | ---: | --- |
| Abstract | 0.15 | Problem, method, one evidence-backed result |
| Introduction | 0.8-1.0 | Concrete gap, contributions, evidence anchors |
| Related Work | 0.6-0.8 | Synthesize nearest prior work only |
| Method | 1.5-2.0 | Definitions, model/algorithm, inference path |
| Experiments Setup | 0.8-1.0 | Datasets, baselines, metrics, protocol |
| Results + Ablations | 1.8-2.2 | Main table, ablation, robustness/failure boundary |
| Limitations/Reproducibility | 0.4-0.6 | Boundaries, compute, availability, ethics |
| Conclusion | 0.15-0.25 | Narrow takeaway |

Put exhaustive hyperparameters, large grids, proofs, long qualitative examples, and failed explorations in the appendix.

## 9-Page Single-Column Budget

Target main-text allocation, excluding references unless venue says otherwise:

| Section | Page Budget | Purpose |
| --- | ---: | --- |
| Abstract | 0.2 | Problem, method, one bounded result |
| Introduction | 1.0-1.2 | Clear motivation, gap, contribution map |
| Background/Related Work | 1.0-1.2 | Concepts plus nearest prior work |
| Method | 2.0-2.4 | More room for notation, algorithm, diagrams |
| Experiments | 2.0-2.4 | Setup, main results, ablations, robustness |
| Analysis/Limitations | 0.8-1.0 | Mechanism, failures, broader impact/ethics |
| Conclusion | 0.2 | Bounded close |

Single-column space reads more slowly; avoid dense walls of equations or long paragraph blocks. Use displayed equations and figures deliberately.

## Appendix Budget

Appendix should be navigable and claim-linked:

- A: Reproducibility checklist, compute, environment, seeds.
- B: Dataset details, preprocessing, licenses, splits.
- C: Baseline implementation and hyperparameters.
- D: Additional ablations, robustness, negative results.
- E: Proofs or derivations.
- F: Qualitative examples and failure cases.
- G: Extra figures/tables.

If appendix exceeds roughly 12 pages, add an appendix table of contents and a one-paragraph guide.

## Triage Rules

- Keep in main: nearest-baseline comparison, method schematic, main result, one mechanism ablation, one limitation/failure boundary.
- Move to appendix: exhaustive metrics, extra datasets when not central, hyperparameter grids, implementation logs, long prompts, examples, proofs too long for main.
- Cut entirely: repeated motivation, duplicated related-work summaries, unverified claims, redundant figures, raw logs.
- Never move a detail required to understand the main claim unless main text includes a clear pointer.

## Output Contract

Write `.research/paper/page_budget.md`:

```markdown
# Conference Page Budget

## Mode
8p-double | 9p-single | appendix

## Section Budget

| Section | Target pages | Current pages/words | Decision |

## Main-vs-Appendix Map

| Content | Main/Appendix | Reason | Artifact |

## Page-Pressure Risks

## Required Cuts Or Moves
```

## Red Lines

- Do not rely on unreadably small fonts, tiny axes, or excessive negative spacing.
- Do not delete limitations, reproducibility, or baseline fairness details to make the paper look stronger.
- Do not claim a venue format without checking the actual call/template when preparing a real submission.
