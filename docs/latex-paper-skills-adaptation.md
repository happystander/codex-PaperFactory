# latex-paper-skills Adaptation

PaperFactory now treats `yunshenwuchuxun/latex-paper-skills` as the external
LaTeX writing engine for late-stage paper production. The skill bundle is
installed under `~/.codex/skills` and its shared runtime helpers live in
`~/.codex/skills/_shared`.

## Installed Skills

| Skill | PaperFactory role |
| --- | --- |
| `paper-from-zero` | Optional routing layer for topic brief, contribution map, evidence matrix, and review-vs-empirical paper choice. |
| `empirical-paper-writer` | Main path for method papers with experiments, ablations, result status, and evidence-safe claims. |
| `arxiv-paper-writer` | Path for survey/review papers and shared LaTeX/citation/QA scripts. |
| `results-backfill` | Upgrades placeholders to factual claims only after verified result files exist. |
| `latex-rhythm-refiner` | Final prose rhythm pass that preserves citations and verified numeric claims. |

## How It Changes PaperFactory

PaperFactory keeps its long-horizon `.research/` state machine, but `paper_drafting`
now requires more structured writing artifacts:

- `paper/claim_evidence_map.md` before prose.
- `paper/writing_issues.csv` as the section/claim/citation/result contract.
- `paper/main.tex` and `paper/ref.bib` alongside the Markdown draft.
- `paper/latex_qa.md` during internal review.

The writing prompt tells Codex to use the external skill bundle when available:

- route unclear deliverables through `paper-from-zero`;
- use `empirical-paper-writer` for experimental papers;
- use `arxiv-paper-writer` for review papers and citation/compile helpers;
- use `results-backfill` to replace placeholders only from verified CSV/JSON
  result files;
- use `latex-rhythm-refiner` only after claims, citations, and numbers are stable.

## Script Reuse

The installed bundle provides deterministic scripts that Codex can call during
`paper_drafting` or `internal_review`:

```bash
python3 ~/.codex/skills/arxiv-paper-writer/scripts/issue_workflow.py --help
python3 ~/.codex/skills/arxiv-paper-writer/scripts/citation_policy.py --help
python3 ~/.codex/skills/arxiv-paper-writer/scripts/source_ranker.py --help
python3 ~/.codex/skills/arxiv-paper-writer/scripts/style_profile.py --help
python3 ~/.codex/skills/arxiv-paper-writer/scripts/compile_paper.py --help
python3 ~/.codex/skills/empirical-paper-writer/scripts/validate_design_csvs.py --help
python3 ~/.codex/skills/empirical-paper-writer/scripts/validate_empirical_paper_issues.py paper/writing_issues.csv
```

Their outputs should be summarized in `.research/paper/latex_qa.md`; raw logs can
stay under `.research/logs/` or the paper build directory.

## Guardrails

- Do not fabricate citations, results, or significance claims.
- Keep `planned`, `placeholder`, and `verified` result states explicit.
- Do not mark writing issues done until dependencies and citation checks pass.
- If LaTeX is unavailable, record that in `paper/latex_qa.md` and keep the
  source files valid enough for later compilation.
