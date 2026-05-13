---
name: research-library-workflow
description: Use when a research phase needs structured literature-library work, ScholarAIO/Zotero/EndNote ingestion, local or federated paper search, workspace construction, citation graph/topic analysis, citation validation, BibTeX/RIS/DOCX export, or source-grounded paper reading. Applies during survey, research-gap analysis, paper evidence assembly, paper drafting, and internal review.
---

# Research Library Workflow

Use this skill to turn loose papers, URLs, PDFs, and citation files into a traceable research library that PaperFactory can use for claims, baselines, and writing.

## Core Rule

Prefer structured library, workspace, citation, and metadata tools over ad hoc PDF piles. If ScholarAIO is installed, use its CLI for real work. If it is unavailable, reproduce the same contracts under `.research/literature/` with explicit provenance.

See `references/scholaraio_skill_map.md` for the condensed ScholarAIO skill map that informed this workflow.

## Operating Workflow

1. Check available tooling with `./paperfactory doctor`, `command -v scholaraio`, and the relevant CLI `--help` command.
2. Ingest sources through the safest path:
   - PDFs, paper bundles, proceedings, patents, theses, standards, lecture notes, and Office files: use an ingest pipeline or record the parser fallback.
   - URLs and online papers: preserve URL, access date, DOI/arXiv ID, and download path.
   - Zotero, EndNote XML, RIS, or BibTeX: import through a structured parser when available.
3. Build a task-specific workspace instead of mixing every paper into one list.
4. Search with fused or multi-source search when available. Separate topical keywords from author/year filters to avoid brittle queries.
5. Read progressively: metadata and abstract first, then conclusion, full text, figures, formulas, and references only as needed.
6. For each important paper or prior-art source, extract task, method, dataset, metric, baseline, limitation, claim, code/checkpoint/data availability, and the exact source anchor.
7. Use topic clustering, citation graph, shared references, and citing-paper trails to find gaps and nearest priors.
8. Before paper drafting or review, run a citation validation pass and classify each citation as verified, ambiguous, missing, or unsupported.
9. Export or maintain BibTeX/RIS/Markdown/DOCX references from the same workspace used for writing.

## PaperFactory Artifacts

During `survey`, strengthen the required artifacts with:

- `.research/literature/library_workspace.md`: workspace name, source imports, search queries, filters, access dates, and included/excluded paper counts.
- `.research/literature/paper_priority_scores.json`: relevance, recency, citation signal, code availability, protocol closeness, and baseline strength.
- `.research/literature/claim_extraction.json`: structured claims with anchors and support status.
- `.research/literature/code_interface_map.md`: data entry, model entry, training command, evaluation command, config system, reusable modules, and incompatibilities.
- `.research/literature/novelty_gap.md`: nearest-prior gap, contradiction, transfer, scale, and feasibility analysis.

During writing and review, add:

- `.research/paper/citation_audit.md`: citation check results, unsupported claims, ambiguous references, and repair decisions.
- `.research/evidence/registry.json`: claim support linked to papers, artifacts, metrics, figures, and paper-safe status.

## Citation Safety

- Treat paper conclusions as claims, not facts.
- A citation supports a sentence only if the cited paper actually contains the method, dataset, metric, result, or limitation being used.
- Do not use a citation merely because its title seems relevant.
- If metadata is uncertain, verify DOI/arXiv/venue/year through at least one primary metadata source before it enters `paper/ref.bib`.
- If the workspace cannot verify a citation, mark it as ambiguous and avoid using it for a main claim.
