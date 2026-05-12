---
name: reviewer-response
description: Draft, audit, or revise point-by-point reviewer response letters, rebuttal packages, revision trackers, editor responses, and manuscript change checklists without inventing experiments, citations, line numbers, or changes.
---

# Reviewer Response

Use this skill after a manuscript receives reviewer or editor comments, or when preparing a rebuttal/revision package.

## Core Rule

Every reviewer concern must be preserved, answered, and mapped to a concrete manuscript change, supplied evidence, justified disagreement, or `AUTHOR_INPUT_NEEDED`.

## Sources Integrated

Condensed from local `nature-response` and PaperFactory audit rules.

## Workflow

1. Identify mode:
   - `draft`;
   - `audit`;
   - `revise`;
   - `triage-only`;
   - `appeal-like`.
2. Split inputs:
   - editor instructions: `E.1`, `E.2`;
   - reviewer comments: `R1.1`, `R1.2`, `R2.1`;
   - author notes and manuscript changes.
3. Classify each item:
   - category;
   - severity;
   - action needed;
   - missing input;
   - response risk.
4. Draft a response strategy summary before prose.
5. Write a point-by-point letter and change checklist.
6. Run QA for completeness, factuality, tone, and traceability.

## Output Contract

```markdown
# Response Strategy Summary

- Decision type:
- Overall posture:
- Major risks:

## Comment-Response Tracker

| ID | Reviewer concern | Type | Severity | Proposed action | Missing input |

## Draft Point-by-Point Response

## Manuscript Change Checklist

## Missing Information / Risk Flags
```

## Tone Rules

- Acknowledge the concern before explaining.
- Be concise and evidence-linked.
- When disagreeing, give scientific or scope-based reasons.
- If a reviewer misunderstood the paper, consider whether the manuscript caused the misunderstanding.

## Red Lines

- Do not claim a revision was made unless supplied or actually edited.
- Do not invent line numbers, figure panels, citations, statistics, or supplementary items.
- Do not use hostile language.
- Do not cite time, money, or convenience as the main reason for not doing a requested experiment.
