---
name: academic-polishing
description: Polish, restructure, translate, or de-AI academic prose in English or Chinese while preserving scientific claims, citations, math, evidence boundaries, and paper section logic.
---

# Academic Polishing

Use this skill when the writing exists but needs clearer academic expression, Chinese-English translation, section logic repair, title/abstract polish, or AI-tone reduction.

## Core Rule

Fix argument before style. Do not hide weak logic under fluent prose.

## Sources Integrated

Condensed from `nature-polishing`, `latex-paper-en`, `typst-paper`, and PaperFactory's conference writing rules.

## Diagnosis Order

1. Paper type: research paper, methods paper, dataset/resource paper, algorithmic system, review.
2. Section job: abstract, introduction, related work, method, results, discussion, conclusion.
3. Claim/evidence/boundary: what is claimed, what supports it, where it fails.
4. Paragraph logic: topic sentence, evidence, interpretation, transition.
5. Sentence polish: grammar, tense, hedging, concision.

## Section Jobs

- Abstract: problem, gap, method, key evidence, implication.
- Introduction: broad context -> specific gap -> why gap matters -> how this work addresses it.
- Related Work: theme and comparison, not paper-by-paper listing.
- Results: what was observed under which protocol.
- Discussion: what results mean, how they relate to prior work, limits.
- Conclusion: contribution, evidence, implication with boundary.

## Polishing Rules

- Preserve citations, labels, equations, metric values, dataset names, and model names.
- Use hedging for bounded evidence: `suggests`, `supports`, `improves under`, `mitigates`.
- Avoid unsupported `SOTA`, `proves`, `solves`, `universally`.
- Avoid repeated metric triples in prose; move them to tables.
- Avoid em-dash-heavy AI tone by default; prefer commas, parentheses, or sentence breaks.

## Output Contract

For short text:

```text
Diagnosis:
- Main issue:

Revised version:
...

Change notes:
- ...
```

For paper sections:

```text
Section-level diagnosis
Paragraph-level revision plan
Revised prose
Claim/evidence risks
```

## Red Lines

- Do not invent claims, data, citations, p-values, or limitations.
- Do not remove caveats that are scientifically important.
- Do not overwrite technical meaning to make prose smoother.
