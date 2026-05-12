---
name: presentation-deck
description: Convert a paper, research summary, or completed PaperFactory evidence package into a conference, lab meeting, journal club, thesis, or group-meeting slide outline or PPTX-ready storyboard with figure selection, speaker notes, and verification checklist.
---

# Presentation Deck

Use this skill when the user wants slides, a talk outline, a paper-sharing deck, or a PPTX-ready storyboard from research outputs.

## Core Rule

The slide deck follows the scientific argument, not the paper's section order.

## Sources Integrated

Condensed from local `nature-paper2ppt`, `scientific-figure`, and conference writing rules.

## Story Spine

1. Why does the problem matter?
2. What gap or bottleneck is unresolved?
3. What did we do?
4. What is the key evidence?
5. Why should the audience trust it?
6. What is reusable or broadly meaningful?
7. What are the boundaries and next steps?

## Output Modes

- `outline`: slide titles and bullets only.
- `storyboard`: slide title, message, figure/table, speaker notes.
- `pptx-ready`: detailed layout instructions and asset paths.
- `qa`: deck readiness and risk checks.

## Figure Selection

Use only figures needed for the story:

- one problem/gap slide;
- one method schematic or pipeline;
- one main result;
- one ablation/mechanism;
- one failure/limitation boundary;
- one takeaway/future-work slide.

## Output Contract

```markdown
# Presentation Storyboard

| Slide | Title | Main Message | Evidence/Asset | Speaker Notes |

## Asset Checklist

## Timing Plan

## Risks / Missing Inputs
```

## Red Lines

- Do not invent figures or results.
- Do not overload slides with all paper metrics.
- Do not turn the deck into a chronological paper summary when a claim-based story is clearer.
