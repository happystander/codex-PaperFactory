---
name: latex-typst-paper
description: Source-aware assistant for existing LaTeX or Typst academic paper projects: compile/export diagnosis, bibliography checks, venue formatting, captions, tables, pseudocode, labels, section logic, grammar, de-AI editing, and submission-readiness repair plans.
---

# LaTeX Typst Paper

Use this skill when the project has `.tex` or `.typ` source and the task involves build, formatting, bibliography, source-preserving edits, or venue-specific paper hygiene.

## Sources Integrated

Condensed from local `latex-paper-en` and `typst-paper` skills.

## Module Router

Choose the smallest matching module:

| Module | Use When |
| --- | --- |
| `compile` | LaTeX/Typst build fails or needs fresh export |
| `bibliography` | missing citations, unused entries, BibTeX/Biber/Hayagriva issues |
| `format` | venue compliance, page limits, fonts, margins |
| `figures` | figure paths, extensions, captions, source-data notes |
| `tables` | booktabs/three-line table, table clarity, metric captions |
| `pseudocode` | algorithm floats, algorithmic/algorithm2e/Typst algorithm blocks |
| `grammar` | surface language fixes |
| `sentences` | long or dense sentence diagnostics |
| `logic` | abstract-introduction-conclusion alignment |
| `literature` | related-work synthesis and gap derivation |
| `experiment` | baseline/ablation/statistics/reporting quality |
| `deai` | reduce AI-writing traces while preserving source syntax |
| `title` | title candidates and signal audit |
| `adapt` | retarget venue or journal |

## Routing Order

When multiple modules apply:

`compile -> bibliography -> format -> figures/tables/pseudocode -> grammar/sentences/deai -> logic/literature/experiment -> title/adapt`

## Source Safety

- Preserve `\cite{}`, `\ref{}`, `\label{}`, math, macros, `@cite`, and Typst labels unless explicitly editing them.
- Prefer review comments and patchable suggestions before broad rewrites.
- Keep compile diagnostics separate from prose edits.
- Report exact commands and exit codes when running build tools.

## Output Style

LaTeX comments:

```tex
% EXPERIMENT [Major]: The baseline comparison omits ...
```

Typst comments:

```typst
// LITERATURE [Major]: This paragraph lists papers without comparison ...
```

## Red Lines

- Do not invent citations, labels, equations, metrics, or compilation success.
- Do not edit generated build output.
- Do not rewrite a whole section when a local source-safe comment is sufficient.
