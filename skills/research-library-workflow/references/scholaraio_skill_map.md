# ScholarAIO Skill Map For PaperFactory

Source inspected: <https://github.com/ZimoLiao/scholaraio/tree/main> on 2026-05-13.

ScholarAIO is an AI-native research terminal organized around reusable skills and the `scholaraio` CLI. PaperFactory should not vendor its full runtime. The useful transfer is the workflow discipline: structured search, library workspaces, progressive reading, citation validation, and exportable evidence.

## Skill Families To Reuse Conceptually

| ScholarAIO area | Representative skills | PaperFactory use |
| --- | --- | --- |
| Discovery | `search`, `websearch`, `arxiv`, `explore` | Multi-source literature discovery and raw query provenance in `survey`. |
| Ingestion | `ingest`, `ingest-link`, `import`, `index`, `enrich`, `scrub`, `rename`, `audit` | Turn PDFs, URLs, Zotero/EndNote/RIS, and proceedings into normalized metadata before reading. |
| Workspace | `workspace`, `show`, `topics`, `graph`, `insights`, `citations` | Maintain task-specific paper subsets, read progressively, cluster topics, inspect refs/citing/shared-refs, and export citations. |
| Prior-art expansion | `patent-search`, `patent-fetch`, `webextract`, `metrics` | Pull patents, web pages, standards-like sources, and library metrics into prior-art or background checks when the research question needs them. |
| Writing | `academic-writing`, `literature-review`, `paper-guided-reading`, `paper-writing`, `research-gap`, `citation-check`, `writing-polish`, `review-response` | Route writing tasks by deliverable and validate citation support before paper claims. |
| Outputs | `draw`, `document`, `poster`, `technical-report`, `publish`, `paper2any` | Produce report/slide/poster-ready material after evidence is stable. |

## Command Patterns

Use these patterns only when `scholaraio` is installed and the local CLI exposes the command.

```bash
scholaraio setup check
scholaraio search --help
scholaraio show --help
scholaraio ws --help
scholaraio pipeline --help
```

Search discipline:

- Prefer fused search for broad discovery.
- Do not combine author names and year filters into the same brittle text query.
- Record query text, source, filters, date, and returned count.
- Use local library results before online expansion when the user already has a curated library.

Workspace discipline:

- Create or reuse a workspace for each research task.
- Keep workspace paper refs separate from generated reports.
- For large workspaces, summarize topic clusters and priority papers instead of loading every full text into context.

Guided reading discipline:

- Confirm the exact paper when the user provides fuzzy keywords.
- Read from metadata to full text progressively.
- Extract metadata, question, assumptions, method, data, metrics, baselines, findings, limitations, future work, figure roles, and relation to the active research task.
- Write notes back into a stable workspace artifact.

Citation-check discipline:

- Validate both metadata and claim support.
- Classify references as verified, ambiguous, missing, or unsupported.
- Repair BibTeX from DOI/arXiv/official metadata when possible.
- Do not treat a matching title as sufficient support for a specific claim.

Research-gap discipline:

- Analyze topic coverage, time trends, method matrices, citation graph holes, shared references, citing papers, and future-work statements.
- Separate knowledge gaps, method gaps, contradictions, transfer gaps, and scale gaps.
- Include feasibility and required evidence, not only novelty language.
