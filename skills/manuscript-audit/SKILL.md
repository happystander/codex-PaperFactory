---
name: manuscript-audit
description: Reviewer-style audit for LaTeX, Typst, Markdown, or PDF academic manuscripts: submission readiness, novelty, literature gap, methodology transparency, evidence support, overclaiming, reproducibility, figures/tables, and revision roadmap.
---

# Manuscript Audit

Use this skill during `internal_review`, before submission, after major paper edits, or whenever the user asks for a serious reviewer-style critique.

## Core Rule

Audit before polishing. Find technical, methodological, claim-level, and cross-section issues before improving style.

## Sources Integrated

Condensed from:

- `paper-audit`: deep-review-first audit, gate decisions, issue bundles, committee lenses.
- `latex-paper-en` and `typst-paper`: source-aware checks.
- `conference-paper-writing`: claim-to-evidence discipline.

## Modes

- `quick-audit`: fast readiness screen.
- `deep-review`: serious reviewer critique with major/moderate/minor issues.
- `gate`: pass/fail submission blocker decision.
- `re-audit`: compare current draft against previous audit.

## Review Lenses

Run all by default unless the prompt narrows scope:

1. Editor screen: pitch, venue fit, fatal flaws, clarity of contribution.
2. Novelty/theory: nearest prior work, pseudo-innovation, contribution precision.
3. Literature: synthesis vs paper list, fair gap, missing baselines.
4. Methodology: data, protocol, statistics, implementation transparency.
5. Logic/evidence: claims, tables/figures, limitations, reproducibility.

## Output Contract

Write `.research/reviews/internal_review.md` or a requested audit file:

```markdown
# Manuscript Audit

## Verdict
PASS | FAIL | NEEDS_MORE_WORK

## Submission Blockers

## Major Issues

## Moderate Issues

## Minor Issues

## Claim-to-Evidence Gaps

## Required Revision Roadmap

## Re-Audit Checklist
```

For every issue, include:

- severity;
- source location or quote when available;
- why it matters;
- concrete fix;
- whether new experiments/data are required.

## Basic Local Check

Run the bundled static checker when source is available:

```bash
python <PLUGIN_ROOT>/scripts/manuscript_check.py paper/paper_draft.md --format markdown
python <PLUGIN_ROOT>/scripts/manuscript_check.py main.tex --format latex
python <PLUGIN_ROOT>/scripts/manuscript_check.py main.typ --format typst
```

Treat script output as mechanical evidence, not as the final review.

## Red Lines

- Do not rewrite the paper as part of audit unless the user explicitly asks.
- Do not invent missing experiments, citations, line numbers, or reviewer positions.
- Do not fail a paper for subjective style preferences when evidence and logic are sound.
