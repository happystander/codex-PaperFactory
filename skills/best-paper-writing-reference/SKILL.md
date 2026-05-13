---
name: best-paper-writing-reference
description: Use curated CCF-A/top AI conference best or outstanding papers as experiment-design and writing references. Helps Codex compare paper structure, experiment matrices, figures, tables, limitations, appendix strategy, and LaTeX source patterns from ICLR, NeurIPS/NIPS, ICML, ACL, and AAAI award papers without copying text.
---

# Best Paper Writing Reference

Use this skill during `method_design`, `paper_evidence`, `paper_drafting`, and `internal_review` when planning experiments, paper structure, figures/tables, limitations, or final writing quality.

## Core Rule

Use award papers as structural references, not as text to imitate. Extract patterns about argument flow, evidence design, figure/table construction, appendix strategy, and claim boundaries. Do not copy prose, captions, equations, or LaTeX macros unless they are generic venue/template mechanics.

## Local Assets

- Manifest: `<PLUGIN_ROOT>/reference_papers/manifest.json`
- Fetch script: `<PLUGIN_ROOT>/scripts/fetch_best_paper_references.py`
- Cache: `<PLUGIN_ROOT>/reference_papers/cache/` (ignored by Git)
- Guide: `<PLUGIN_ROOT>/docs/best-paper-writing-references.md`

Fetch references when the cache is missing:

```bash
python <PLUGIN_ROOT>/scripts/fetch_best_paper_references.py --limit 7
```

For a lighter pass:

```bash
python <PLUGIN_ROOT>/scripts/fetch_best_paper_references.py --pdf-only --venue ACL
python <PLUGIN_ROOT>/scripts/fetch_best_paper_references.py --metadata-only
```

## What To Extract

For each relevant paper, write short notes only:

- paper type: method, empirical scaling, theory, position, diagnostic, benchmark;
- introduction funnel: problem hook, gap, contribution wording;
- experiment design: datasets, baseline tiers, ablations, robustness, efficiency, negative results;
- table design: main comparison, ablation, diagnostic, cost/efficiency, statistical reporting;
- figure design: method overview, result trend, mechanism, failure boundary;
- limitation/reproducibility treatment;
- appendix/source organization from LaTeX source when available.

## Output Contract

Write reference notes under the active research directory:

```markdown
# Best Paper Reference Notes

## Papers Consulted

| Paper | Venue | Why consulted |

## Experiment Design Patterns

## Writing Structure Patterns

## Figure/Table Patterns

## Limitations And Reproducibility Patterns

## Patterns To Reuse In This Project

## Patterns Not Applicable
```

Use `.research/method/best_paper_experiment_notes.md` during method/experiment design and `.research/paper/best_paper_style_notes.md` during drafting/review.

## Red Lines

- Do not treat award papers as evidence for this project's scientific claims unless they are directly relevant prior work.
- Do not invent award status; rely on the manifest's `award_evidence_url` and update it if a better official source is found.
- Do not add downloaded PDFs or source bundles to Git.
- Do not quote long passages. Summarize structure and reusable patterns in your own words.
