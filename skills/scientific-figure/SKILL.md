---
name: scientific-figure
description: Create, revise, or audit publication-quality scientific figures for research papers, including figure contracts, source-data manifests, Python matplotlib styling, multi-panel logic, captions, export QA, and honest failure-boundary visualization.
---

# Scientific Figure

Use this skill when the research workflow needs paper-ready figures, high-quality scientific plots, figure plans, captions, or source-data manifests.

## Core Rule

A figure is a visual argument. Start from the claim, then choose panels and style. Do not create attractive plots that do not carry a specific piece of evidence.

## Figure Contract

Before plotting, write `.research/figures/figure_plan.md` with:

- Core conclusion: one sentence the figure must defend.
- Evidence chain: which artifact or source data supports each panel.
- Figure archetype: `main comparison`, `ablation`, `mechanism`, `robustness`, `failure boundary`, `qualitative case`, or `method schematic`.
- Panel map: panel label, input file, chart type, metric, and takeaway.
- Review risks: missing seeds, non-comparable protocols, saturated axis, cherry-picked cases, or unclear statistics.
- Export target: single-column, double-column, appendix, slide, or supplementary.

## Source Data

Every paper figure must have traceable source data. Maintain `.research/figures/source_data_manifest.json`:

```json
{
  "figures": [
    {
      "figure_id": "fig1",
      "panel": "a",
      "source": ".research/experiments/cheap_baselines/metrics.json",
      "script": ".research/figures/scripts/plot_fig1.py",
      "outputs": [".research/figures/fig1.svg", ".research/figures/fig1.pdf"],
      "notes": "Protocol-matched main comparison."
    }
  ]
}
```

## Python Style Defaults

Use Python/matplotlib by default for autonomous runs unless the user or project explicitly requires R.

Default physical sizes:

- Single-column: 8.5 cm x 6.375 cm.
- Double-column: 17.8 cm x 10.5 cm.
- Appendix grid: choose the smallest size that keeps labels readable.

Typography and export:

- Prefer Arial/Helvetica/DejaVu Sans fallback.
- Use editable text in SVG and TrueType fonts in PDF: `svg.fonttype = "none"`, `pdf.fonttype = 42`.
- Use 7-8 pt text for dense conference figures; use 12 pt only for standalone single-chart reports that will not be shrunk.
- Export SVG and PDF for paper source; export PNG/TIFF only for preview or journal requirements.

Axes and legends:

- Use direct labels when category positions are stable.
- Keep legends frameless and compact.
- Avoid 3D bars, heavy backgrounds, rainbow palettes, and decorative gradients.
- Use color and line style together when categories must survive grayscale printing.
- Do not truncate axes unless the caption and visual encoding make the truncation explicit.

Color defaults:

- Main signal: `#2563EB`
- Positive/gain: `#16A34A`
- Negative/drop: `#DC2626`
- Neutral: `#525252`
- Secondary: `#7C3AED`
- Light backgrounds: `#EFF6FF`, `#F0FDF4`, `#FEFCE8`

## Plot Types

Main comparison:

- Prefer horizontal bars or compact tables when method names are long.
- Sort by the primary metric, but keep baseline groups visually separated when fairness matters.
- Show confidence intervals or seed variation when available.

Ablation:

- Plot deltas relative to the full method when the mechanism claim matters.
- Include a no-op/full baseline line.

Trend or scaling:

- Use line plots with markers only when sample density is low.
- Label monotonicity or saturation directly.

Failure boundary:

- Show where the method fails and where it improves.
- Avoid hiding negative cases in appendix-only figures when they bound the main claim.

Qualitative cases:

- Choose cases by documented criteria, not by appearance alone.
- Include success, failure, and boundary examples.

## Caption Policy

Each caption should include:

- takeaway sentence;
- dataset/protocol;
- metric definition and cutoff;
- seed/statistics note if applicable;
- source-data pointer or appendix reference;
- limitations when the figure is diagnostic.

## Autonomous Workflow Integration

During `paper_evidence`, produce or update:

- `.research/figures/figure_plan.md`
- `.research/figures/source_data_manifest.json`
- `.research/figures/scripts/`
- `.research/figures/*.svg` and `.research/figures/*.pdf` when dependencies are available

If plotting dependencies are missing, write the script and record the blocker in the phase report instead of fabricating a rendered figure.
