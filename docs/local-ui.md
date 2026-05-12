# Local UI And Launcher

PaperFactory includes a dependency-light launcher at the repository root:

```bash
/path/to/codex-PaperFactory/paperfactory --help
```

It wraps the lower-level scripts so daily operation does not require remembering Python file paths.

## Common Flow

```bash
/path/to/codex-PaperFactory/paperfactory new --task "your research task"
/path/to/codex-PaperFactory/paperfactory status --logs 8
/path/to/codex-PaperFactory/paperfactory prompt --copy
/path/to/codex-PaperFactory/paperfactory log --action "checked results" --outcome "ready for review"
/path/to/codex-PaperFactory/paperfactory run --once
/path/to/codex-PaperFactory/paperfactory dashboard --open
/path/to/codex-PaperFactory/paperfactory web --open
```

The generated dashboard is a static HTML file at:

```text
.research/dashboard.html
```

It shows the active phase, gate status, missing artifacts, phase progress, recent audit log entries, and the next operational commands.

## Interactive Web UI

The interactive UI starts a local server. The default page is a concise Chinese agent-style console:

```bash
/path/to/codex-PaperFactory/paperfactory web --host 127.0.0.1 --port 8765 --open
```

It provides:

- start/pause buttons for autonomous Codex cycles;
- detached background execution, so a started run continues after the browser tab or Web UI server is closed;
- a concise Chinese agent-style interface with a left-side file tree and a phase flow;
- Codex-authored natural-language progress from `.research/progress/feed.jsonl`; raw logs remain available only for diagnostics;
- cycle count, interval, and optional run-duration controls;
- memory switches for summary, logs, human interventions, and current artifacts;
- human intervention messages saved to `.research/human_interventions.md` and injected into the next generated prompt;
- task editing that updates both `.research/task.md` and `.research/state.json`;
- artifact browsing and text preview for files under `.research/`;
- figure browsing for `.svg`, `.pdf`, `.png`, `.jpg`, `.jpeg`, and `.webp` files under `.research/figures/`;
- automatic `manuscript-audit` review in `internal_review` after paper drafting is complete.

For a non-destructive UI test, enable `Dry run` before clicking `Start`. Dry-run mode refreshes prompts without invoking `codex exec`.

Human intervention takes effect on the next cycle. To force an immediate course correction, pause the background process, send the intervention, then start a new cycle.

The user-facing progress feed is:

```text
.research/progress/feed.jsonl
```

Codex is instructed to append one JSON object per line with a natural-language `message`. The UI renders that feed directly.

The automatic top-conference review is written during `internal_review`:

```text
.research/reviews/top_conference_review.md
```

## Tool Wrappers

The launcher also exposes the helper tools through one command:

```bash
/path/to/codex-PaperFactory/paperfactory bib -- --bib references.bib --query "retrieval augmented generation"
/path/to/codex-PaperFactory/paperfactory check -- paper/paper_draft.md --format markdown
/path/to/codex-PaperFactory/paperfactory plot -- --input metrics.csv --x method --y score --output .research/figures/main
```

The `--` separator is optional for positional inputs, but it keeps forwarded tool options visually separate from launcher options.

## Diagnostics

```bash
/path/to/codex-PaperFactory/paperfactory doctor
```

`doctor` checks Python, the plugin manifest, Git, Codex CLI availability, and optional plotting support.
