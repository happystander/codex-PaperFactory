# Local Skill Integration Notes

This repository was iterated after scanning local `lyq` user skill inventories under:

- `/home/lyq/.codex/skills`
- `/home/lyq/.codex/.tmp/plugins`
- `/home/lyq/.claude/plugins`
- `/data3/lyq/workspace/codex_workspace/auto_research/generative_rec_agent_research/external`
- `/data3/lyq/workspace/codex_workspace/auto_research/KLC论文写作自查.pdf`

The scan found 500+ `SKILL.md` files. Most were unrelated to academic writing (frontend, cloud, mobile, payments, service APIs). PaperFactory integrates the writing-relevant ideas as concise plugin-local skills rather than copying large third-party skill bodies.

## Integrated Skill Families

| PaperFactory skill | Local sources condensed | Purpose |
| --- | --- | --- |
| `paper-reader` | `nature-reader`, `huggingface-papers`, `auto-research` | Source-grounded paper reading and baseline extraction |
| `llm-rl-toolkit` | `chengyuZou/Open-LLM`, official TRL/verl/ms-swift/LLaMA-Factory/OpenRLHF docs | LLM/Agent/RAG/RL resource routing and mature framework selection before custom infrastructure |
| `citation-workflow` | `bib-search-citation`, `nature-citation`, `zotero`, `huggingface-papers` | Citation search, support grading, BibTeX/Typst/LaTeX snippets |
| `scientific-figure` | `plot`, `nature-figure`, conference writing rules | Figure contracts, source-data manifests, export QA |
| `drawio-academic-skills` | `bahayonghang/drawio-skills` | Editable Draw.io bundles for paper architecture, workflow, roadmap, and method diagrams |
| `best-paper-writing-reference` | Curated CCF-A/top AI award-paper references | Experiment design and paper-writing structure patterns from ICLR, NeurIPS/NIPS, ICML, ACL, and AAAI |
| `conference-paper-writing` | existing project `conference-paper-writing`, academic writing skills, generic rules from `generative_rec_agent_research/skills/conference-paper-writing` | Claims-to-evidence drafting for ML/AI papers |
| `conference-page-budget` | conference writing/page-budget requirements | 8-page double-column, 9-page single-column, and appendix layout planning |
| `latex-typst-paper` | `latex-paper-en`, `typst-paper` | Source-aware paper hygiene and format checks |
| `paper-format-self-check` | `KLC论文写作自查.pdf` | Final source/PDF submission hygiene: quotes, abbreviations, BibTeX venue cleanup, published-version citations, nonbreaking references, figure/table readability, appendix navigation, list spacing, and cropping |
| `academic-polishing` | `nature-polishing`, LaTeX/Typst expression modules | Claim-safe polishing, translation, title/abstract cleanup |
| `data-availability` | `nature-data` | Data/code/model availability and FAIR metadata |
| `manuscript-audit` | `paper-audit`, source-aware paper skills | Reviewer-style gate and revision roadmap |
| `reviewer-response` | `nature-response` | Point-by-point response packages |
| `presentation-deck` | `nature-paper2ppt`, figure/story rules | Paper-to-talk storyboard/PPT-ready planning |
| `paper-from-zero` | `yunshenwuchuxun/latex-paper-skills` | Topic brief, contribution map, evidence matrix, and review/empirical routing |
| `empirical-paper-writer` | `yunshenwuchuxun/latex-paper-skills` | Evidence-first empirical paper contract, result status, issue-driven writing |
| `arxiv-paper-writer` | `yunshenwuchuxun/latex-paper-skills` | Review paper workflow plus reusable LaTeX, BibTeX, citation, and compile scripts |
| `results-backfill` | `yunshenwuchuxun/latex-paper-skills` | Replace placeholders with verified experiment results and generate result material |
| `latex-rhythm-refiner` | `yunshenwuchuxun/latex-paper-skills` | Final prose rhythm pass that preserves citation positions and verified numbers |

## Deliberately Not Integrated

- Product/API/platform skills unrelated to academic writing.
- Domain-specific life-science database skills, because PaperFactory should stay field-agnostic.
- Most of `generative_rec_agent_research/skills/mllm-user-sim-rec`, because it is a project memory for MLLM recommender research. Only generic writing discipline already present in PaperFactory was retained: no drafting before evidence gates, identical-protocol comparisons, strong baseline coverage, negative-result scoping, and claim-safe appendix strategy.
- External scripts that are not writing-critical. The `latex-paper-skills` writing engine is installed as a sibling skill bundle instead of being vendored wholesale into this repository.

## Added Local Helpers

- `scripts/bib_query.py`: dependency-free BibTeX search and citation snippets.
- `scripts/manuscript_check.py`: lightweight manuscript hygiene checks.
- `scripts/manuscript_check.py`: now also flags KLC-style mechanical issues such as smart quotes, malformed `i.e.,`/`e.g.,`, breakable LaTeX references, raw `resizebox`, loose `itemize`, arXiv-preprint bibliography entries, and noisy `booktitle` fields.
- `scripts/make_metric_plot.py`: simple metric plotting with paper-style exports.
- `scripts/fetch_best_paper_references.py`: downloads curated award-paper PDFs and arXiv source bundles into the ignored local cache `reference_papers/cache/`.
- `llm-rl-toolkit`: summarizes Open-LLM into a task map and adds a framework selector for TRL, verl, ms-swift, LLaMA-Factory, and OpenRLHF.
- `paperfactory doctor`: checks whether the external `latex-paper-skills` bundle and its `_shared` runtime helpers are installed.
- `paperfactory doctor`: also reports optional open research tools for literature APIs, PDF extraction, LaTeX builds, experiment tracking, workflow orchestration, and artifact versioning.
- `docs/open-research-tooling.md`: maps open-source research tools to PaperFactory phases and defines fallback rules when optional tools are unavailable.
- `drawio-academic-skills`: installed as an external sibling skill; PaperFactory checks for its CLI and asks Codex to preserve editable diagram bundles.

## Maintenance Rule

Keep PaperFactory skills concise. If a future integration requires long venue-specific rules, place them in `docs/` or `templates/` and reference them from the skill, rather than expanding `SKILL.md` past the point where it becomes expensive to load.
