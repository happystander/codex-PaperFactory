---
name: paper-format-self-check
description: Run a submission-format self-check for academic manuscripts, especially LaTeX/PDF papers, covering KLC-style quote hygiene, BibTeX venue cleanup, published-version citations, reference line breaks, figure/table readability, appendix organization, list spacing, and final PDF visual inspection.
---

# Paper Format Self Check

Use this skill during `paper_drafting`, `internal_review`, and final submission cleanup, after the scientific claim/evidence audit but before camera-ready or submission packaging.

## Core Rule

Format cleanup must not change scientific meaning. Fix visual, LaTeX, BibTeX, and consistency defects only after claims, citations, and numbers are stable.

## Sources Integrated

Condensed from `KLC论文写作自查.pdf` plus PaperFactory LaTeX, figure, and conference-writing rules.

## Checklist

Run these checks on both source and rendered PDF when possible:

1. Quotes: in LaTeX source use ``quoted text'' rather than curly smart quotes or raw double quotes.
2. Line breaks: inspect the PDF for orphan one-word lines; repair by light rephrasing, not by meaning-changing edits.
3. English spacing: leave a space before parenthetical text in prose, e.g. `method (ours)`.
4. Bibliography venue fields: manually clean noisy `booktitle` entries; prefer consistent conference names such as `Proceedings of the ... (ACL)`.
5. Published versions: if a paper has appeared at a venue, cite the published conference/journal version rather than an arXiv preprint unless arXiv is the only version.
6. Reference style consistency: use one style for the same source type across the bibliography.
7. Abbreviations: use `i.e.,` and `e.g.,` exactly, not `ie.`, `i e.,`, or `i.e,`.
8. Figure readability: axis labels, ticks, legends, and annotations must remain readable at final paper size.
9. Bar charts: distinguish categories with color plus shape, hatch, marker, or direct labels so the figure survives grayscale/printing.
10. Headings: capitalization and terminal punctuation must be consistent within the same heading level.
11. Appendix: long appendices should have a table of contents or clear appendix navigation.
12. Tables: only use `\resizebox` when the table would otherwise overflow; do not enlarge naturally fitting tables.
13. References in prose: use nonbreaking spaces such as `Table~\ref{...}`, `Figure~\ref{...}`, `Section~\ref{...}`, and `Eq.~\ref{...}`.
14. Lists: if `itemize` spacing is too loose, use `enumitem` with `[noitemsep,nolistsep]` or a venue-safe equivalent.
15. Figure whitespace: crop excessive blank margins in figures so paper-space is not wasted.

## Automated Source Check

Run the bundled checker when source is available:

```bash
python <PLUGIN_ROOT>/scripts/manuscript_check.py paper/main.tex --format latex
python <PLUGIN_ROOT>/scripts/manuscript_check.py paper/paper_draft.md --format markdown
```

Treat script output as a triage list. The rendered PDF still needs visual inspection for line breaks, tiny axes, table overflow, appendix navigation, and figure cropping.

## Output Contract

Write results to `.research/paper/format_self_check.md`:

```markdown
# Paper Format Self Check

## Source Checks

## Rendered PDF Checks

## Bibliography Checks

## Figure And Table Checks

## Required Fixes

| Severity | Location | Issue | Fix | Status |

## Residual Risks
```

## Red Lines

- Do not invent venue metadata, DOI fields, page numbers, or publication status.
- Do not silently convert arXiv citations to venue citations without checking a reliable source such as the official paper page, publisher page, DBLP, Crossref, OpenAlex, or Semantic Scholar.
- Do not use `\resizebox` or aggressive spacing only to hide content-density problems.
