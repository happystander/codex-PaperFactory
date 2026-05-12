# Codex PaperFactory Operating Rules

When working inside a project that uses this plugin:

- Treat `.research/` as the source of truth for task state, logs, gates, and artifacts.
- Append to `.research/logs/research.log` for every meaningful action.
- Prefer real datasets, official repositories, paper PDFs, model cards, and benchmark pages over secondary summaries.
- Never report proxy, smoke, diagnostic, or failed runs as final evidence.
- Preserve scripts, configs, raw outputs, metrics, plots, and paper drafts under `.research/` or project experiment directories.
- Do not draft or polish a paper until data sanity, baselines, method evidence, ablations, and comparison gates are present.
- If a phase is blocked, write the blocker to the phase report and leave a concrete next action.
