---
name: citation-workflow
description: Manage research citations for paper writing: search BibTeX/Zotero-exported libraries, map manuscript claims to supporting papers, generate LaTeX/Typst citation snippets, audit citation support, and prepare reference-manager-ready notes without inventing sources.
---

# Citation Workflow

Use this skill when a research phase needs bibliography search, citation insertion, claim-to-reference mapping, `.bib` cleanup, Zotero-exported library search, or citation support auditing.

## Core Rule

Never cite a paper as support just because its title is related. A citation must support the exact claim or be labeled as background, partial, contradictory, or metadata-only.

## Sources Integrated

This skill condenses useful patterns from local skills:

- `bib-search-citation`: `.bib` search, compact filters, LaTeX/Typst citation snippets.
- `nature-citation`: claim segmentation and conservative support grading.
- `zotero`: Zotero-exported BibTeX and local-library workflow.
- `huggingface-papers`: AI paper metadata, linked models/datasets/repos, arXiv/HF paper pages.

## Workflow

1. Inventory available sources:
   - `.bib` files such as `references.bib`, `paper.bib`, or Zotero exports;
   - `.research/literature/*.md`;
   - arXiv/Hugging Face paper URLs or IDs;
   - Zotero library exports if provided.
2. Segment manuscript text into citable claims:
   - one claim per segment;
   - preserve stable IDs such as `C001`, `C002`;
   - skip connective sentences unless the user asks to cite every sentence.
3. Search candidate references:
   - use `scripts/bib_query.py` for local `.bib` search;
   - use primary-source web/API lookups when local bibliography is insufficient;
   - prefer official paper pages, arXiv, DOI metadata, publisher pages, and official repos.
4. Grade support:
   - `strong support`: directly tests or establishes the claim;
   - `partial support`: narrower condition or only part of claim;
   - `background support`: field context only;
   - `contradictory/limiting`: conflicts or narrows claim;
   - `metadata-only`: title/metadata suggests relevance, but abstract/full text was not checked.
5. Write outputs under `.research/citations/`:
   - `claim_reference_map.md`;
   - `citation_candidates.json`;
   - `references_to_add.bib` when applicable.

## Local BibTeX Search

Use the bundled stdlib script:

```bash
python <PLUGIN_ROOT>/scripts/bib_query.py \
  --bib references.bib \
  --query "vision language recommendation" \
  --year-min 2022 \
  --has doi \
  --limit 10 \
  --format markdown
```

Useful filters:

- `--author Cheng`
- `--year-min 2024`
- `--year-max 2026`
- `--has doi`
- `--has eprint`
- `--format json|markdown|keys`

## Citation Snippets

For LaTeX, provide:

```tex
\cite{key}
\parencite{key}
\textcite{key}
```

For Typst, provide:

```typst
@key
#cite(<key>)
```

Use explicit label-style forms when a key contains fragile punctuation.

## Output Contract

When adding or auditing citations, return:

```text
Citation map
| Claim ID | Claim | Citation key(s) | Support grade | Notes |

References to add
- key: title, year, venue, DOI/arXiv, why it supports the claim

Risks
- unsupported claim, over-broad citation, stale metadata, or missing primary source
```

## Red Lines

- Do not invent BibTeX entries, DOI, arXiv IDs, venues, or author lists.
- Do not silently replace an unsupported claim with a loosely related citation.
- Do not rewrite citation keys unless the user explicitly asks for bibliography normalization.
