# Best Paper Writing References

PaperFactory keeps a small, fetchable reference set of CCF-A/top AI conference award papers for writing and experiment-design guidance. The goal is not to copy text. The goal is to let Codex inspect how strong papers structure claims, experiments, figures, tables, limitations, and appendices.

## How To Fetch

```bash
python scripts/fetch_best_paper_references.py
```

Downloaded files are written to:

```text
reference_papers/cache/
```

The cache is ignored by Git. The committed file is only the manifest:

```text
reference_papers/manifest.json
```

## Curated Set

| Venue | Year | Award Paper | Primary Use |
| --- | ---: | --- | --- |
| NeurIPS/NIPS | 2017 | Attention Is All You Need | Architecture figure, ablations, concise method exposition |
| NeurIPS | 2020 | Language Models are Few-Shot Learners | Large-scale experiments, limitations, broader impact, appendix-heavy evidence |
| ICLR | 2017 | Understanding Deep Learning Requires Rethinking Generalization | Hypothesis-driven empirical design and figure-led argument |
| ICML | 2017 | Understanding Black-box Predictions via Influence Functions | Theory-to-practice method motivation and case studies |
| ACL | 2020 | Climbing towards NLU | Position-paper definitions, field critique, claim scoping |
| ACL-IJCNLP | 2021 | Vocabulary Learning via Optimal Transport for Neural Machine Translation | Efficiency experiments, main result tables, code availability |
| AAAI | 2023 | Misspecification in Inverse Reinforcement Learning | Formal problem setup, assumptions, theorem-driven structure |

## Codex Use Rules

- During `method_design`, compare the project’s planned experiments against the reference set’s baseline tiers, ablations, robustness checks, and failure-boundary reporting.
- During `paper_evidence`, compare figures and tables against the reference set’s role: method overview, main result, ablation, diagnostic, cost, or limitation.
- During `paper_drafting`, inspect the introduction funnel, contribution wording, limitations, and appendix strategy.
- During `internal_review`, ask whether the current paper would look thin compared with these references in baseline coverage, statistical evidence, figure readability, or claim boundaries.

Codex should write short notes to:

```text
.research/method/best_paper_experiment_notes.md
.research/paper/best_paper_style_notes.md
```

## Copyright And Repository Hygiene

Do not commit downloaded PDFs or LaTeX/e-print source bundles. Keep them in the ignored cache and summarize only reusable writing/experiment patterns.
