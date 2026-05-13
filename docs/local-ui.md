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
- a concise Chinese agent-style interface with explicit running state, PID, last activity, a left-side file tree, and a phase flow;
- per-phase display pages at `/phase?key=<phase>`, backed by `.research/pages/<phase>.md` when Codex has written one and by a fallback artifact/report summary otherwise;
- a locked base workflow plus user-inserted custom phases; custom phase prompts live in `.research/workflow.json` and affect later prompt generation and phase advancement;
- project switching across nearby `.research/` workspaces, so each research task can keep its own prompt memory settings;
- Codex status monitoring from `~/.codex/sessions`, including active-session quota, reset time, context window, and token usage;
- Codex-authored natural-language progress from `.research/progress/feed.jsonl`; the chat area does not synthesize progress or render raw logs;
- cycle count, interval, and optional run-duration controls;
- friendly memory profiles for light, standard, deep, and clean-start modes. Every mode starts from the generated `.research/memory/handoff.md`; stronger modes add phase summaries, artifact index, decision/risk memory, claim/evidence notes, logs, and current artifacts;
- human intervention messages saved to `.research/human_interventions.md` and injected into the next generated prompt;
- structured intervention patches saved to `.research/interventions/patches.jsonl`, so user changes can target scope, workflow, memory, or stop conditions instead of remaining as plain chat history;
- runtime control files visible in the file tree: `.research/workflow_state.json`, `.research/evidence/registry.json`, `.research/queue/tasks.jsonl`, and `.research/control/stop_conditions.json`;
- task editing that updates both `.research/task.md` and `.research/state.json`;
- artifact browsing with full-page preview for text, image, SVG, and PDF files under `.research/`;
- figure browsing for `.svg`, `.pdf`, `.png`, `.jpg`, `.jpeg`, and `.webp` files under `.research/figures/`;
- automatic `manuscript-audit` and `paper-format-self-check` review in `internal_review` after paper drafting is complete.
- conference page-budget and curated award-paper reference prompts for late-stage writing.

For a non-destructive UI test, enable `Dry run` before clicking `Start`. Dry-run mode refreshes prompts without invoking `codex exec`.

Human intervention takes effect on the next cycle. To force an immediate course correction, pause the background process, send the intervention, then start a new cycle.

The generated cross-phase memory bundle can be refreshed manually:

```bash
/path/to/codex-PaperFactory/paperfactory memory
```

It writes `.research/memory/handoff.md`, `phase_summaries.jsonl`, `artifact_index.json`, `decision_memory.json`, `risk_memory.json`, and `claim_memory.json`. This is the handoff layer between stages; Codex should persist important findings in artifacts and reports so this bundle can carry them into later cycles.

The user-facing progress feed is:

```text
.research/progress/feed.jsonl
```

Codex is instructed to append one JSON object per line with a natural-language `message`. The UI renders that feed directly and shows an empty state until Codex writes an event.

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
