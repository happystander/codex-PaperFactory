# Refactor Roadmap

PaperFactory is moving from script-sized files toward a small modular Python
application while keeping the existing `paperfactory` CLI and Web UI behavior
stable.

## Current Pain Points

| Area | Current Shape | Problem |
| --- | --- | --- |
| `scripts/paperfactory_web.py` | HTTP handler, process control, Codex status parsing, HTML/CSS/JS templates, file preview, memory profiles, job orchestration. | Too many reasons to change one file; UI edits can accidentally affect backend behavior. |
| `scripts/researchctl.py` | Workflow definitions, state IO, memory generation, prompt generation, route advancement, validation. | Controller responsibilities are mixed with generated-memory and prompt-construction details. |
| `scripts/paperfactory.py` | CLI launcher, dashboard renderer, Codex loop runner, dependency doctor, command delegation. | Usable, but should eventually become a thin command adapter. |
| Embedded Web assets | Large HTML/CSS/JS strings inside Python. | Hard to review, test, or iterate visually. |

## Target Module Layout

```text
scripts/
  paperfactory.py                 # CLI adapter
  paperfactory_web.py             # HTTP adapter only
  researchctl.py                  # controller adapter only
  paperfactory_core/
    memory.py                     # generated cross-phase memory bundle
    web_memory.py                 # Web memory profile config
    workflow.py                   # phase definitions and custom phase config
    state.py                      # state, logs, report IO
    prompts.py                    # phase prompt construction
    jobs.py                       # detached run lifecycle
    codex_status.py               # Codex session/quota parsing
    artifacts.py                  # tree, preview, figure/artifact listing
    web_assets/                  # HTML/CSS/JS templates
```

## Refactor Sequence

| Step | Status | Scope | Safety Check |
| --- | --- | --- | --- |
| 1 | Done | Extract generated memory bundle from `researchctl.py` into `paperfactory_core/memory.py`; extract Web memory profiles into `paperfactory_core/web_memory.py`. | Existing CLI/Web tests plus manual `paperfactory memory --json`. |
| 2 | Next | Extract workflow phase definitions, custom phase config, and route normalization into `paperfactory_core/workflow.py`. | `researchctl_test.py` must prove custom phase insertion, skip, jump, and repeat still work. |
| 3 | Next | Extract state/report/log IO into `paperfactory_core/state.py`. | Init, status, advance, validate, and memory refresh tests. |
| 4 | Next | Extract prompt construction into `paperfactory_core/prompts.py`. | Golden prompt smoke assertions for memory reads, cleanup contract, progress feed, custom prompt, and phase route schema. |
| 5 | Next | Extract detached run lifecycle and PID handling into `paperfactory_core/jobs.py`. | Web start/stop tests and dry-run background job smoke tests. |
| 6 | Next | Extract Codex session/quota parsing into `paperfactory_core/codex_status.py`. | Unit fixtures for token_count JSONL parsing and missing-session fallback. |
| 7 | Next | Move artifact tree, file preview, figure listing, and phase page rendering into `paperfactory_core/artifacts.py`. | Web artifact/preview tests for text, SVG, PDF, and missing files. |
| 8 | Next | Move embedded UI strings to `paperfactory_core/web_assets/` or a tiny template layer. | Web smoke test plus browser screenshot/manual UI check. |
| 9 | Next | Turn `scripts/paperfactory.py`, `scripts/researchctl.py`, and `scripts/paperfactory_web.py` into thin adapters. | Full smoke suite and `./paperfactory doctor`. |

## Rules For Each Step

- Keep public commands stable: `paperfactory new/status/prompt/run/advance/memory/web/doctor`.
- Move one responsibility per commit.
- Add or preserve a smoke test for the behavior being moved.
- Do not rewrite UI and backend behavior in the same step.
- Prefer pure functions in `paperfactory_core/`; adapters should parse args, call core logic, and print/send responses.
- Generated `.research/` artifacts remain backward compatible unless a migration is explicitly added.

