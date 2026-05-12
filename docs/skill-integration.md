# Local Skill Integration Notes

This repository was iterated after scanning local `lyq` user skill inventories under:

- `/home/lyq/.codex/skills`
- `/home/lyq/.codex/.tmp/plugins`
- `/home/lyq/.claude/plugins`
- `/data3/lyq/workspace/codex_workspace/auto_research/generative_rec_agent_research/external`

The scan found 500+ `SKILL.md` files. Most were unrelated to academic writing (frontend, cloud, mobile, payments, service APIs). PaperFactory integrates the writing-relevant ideas as concise plugin-local skills rather than copying large third-party skill bodies.

## Integrated Skill Families

| PaperFactory skill | Local sources condensed | Purpose |
| --- | --- | --- |
| `paper-reader` | `nature-reader`, `huggingface-papers`, `auto-research` | Source-grounded paper reading and baseline extraction |
| `citation-workflow` | `bib-search-citation`, `nature-citation`, `zotero`, `huggingface-papers` | Citation search, support grading, BibTeX/Typst/LaTeX snippets |
| `scientific-figure` | `plot`, `nature-figure`, conference writing rules | Figure contracts, source-data manifests, export QA |
| `conference-paper-writing` | existing project `conference-paper-writing`, academic writing skills | Claims-to-evidence drafting for ML/AI papers |
| `latex-typst-paper` | `latex-paper-en`, `typst-paper` | Source-aware paper hygiene and format checks |
| `academic-polishing` | `nature-polishing`, LaTeX/Typst expression modules | Claim-safe polishing, translation, title/abstract cleanup |
| `data-availability` | `nature-data` | Data/code/model availability and FAIR metadata |
| `manuscript-audit` | `paper-audit`, source-aware paper skills | Reviewer-style gate and revision roadmap |
| `reviewer-response` | `nature-response` | Point-by-point response packages |
| `presentation-deck` | `nature-paper2ppt`, figure/story rules | Paper-to-talk storyboard/PPT-ready planning |

## Deliberately Not Integrated

- Product/API/platform skills unrelated to academic writing.
- Domain-specific life-science database skills, because PaperFactory should stay field-agnostic.
- Full external scripts that depend on their original plugin layout. PaperFactory instead includes small stdlib helpers where useful.

## Added Local Helpers

- `scripts/bib_query.py`: dependency-free BibTeX search and citation snippets.
- `scripts/manuscript_check.py`: lightweight manuscript hygiene checks.
- `scripts/make_metric_plot.py`: simple metric plotting with paper-style exports.

## Maintenance Rule

Keep PaperFactory skills concise. If a future integration requires long venue-specific rules, place them in `docs/` or `templates/` and reference them from the skill, rather than expanding `SKILL.md` past the point where it becomes expensive to load.
