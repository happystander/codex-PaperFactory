# Long-Horizon Operating Model

This plugin borrows the useful parts of the original `claude-codex` code-review pipeline:

- Explicit phases instead of free-form wandering.
- File-backed task state instead of relying on chat context.
- Gate reports that block premature advancement.
- Independent review before completion.
- A loop script for resumable unattended operation.

The research version changes the unit of work:

| Code-review pipeline | Research pipeline |
| --- | --- |
| Requirements | Research scope and success criteria |
| Plan | Baseline and experiment plan |
| Plan review | Novelty, fairness, and feasibility gate |
| Implementation | Method, baselines, experiments |
| Code review | Evidence and paper review |
| Final Codex gate | Internal adversarial review |

The controller is intentionally conservative. It cannot decide that an idea is publishable by itself; it keeps Codex working on the next auditable artifact and prevents a paper draft from outrunning the evidence.

## Local Auto-Research Pattern

The plugin also follows the project-local auto-research pattern used in the existing workspace:

- A persistent `logs/research.log` records every material action.
- A periodic loop checks whether experiments are still active before launching more work.
- Completed artifacts are post-processed into durable summaries.
- Idempotent relaunch logic is preferred for shard-like jobs.
- Minimal validation runs after automation changes.
- Paper material is assembled from saved metrics and summaries, not from chat memory.

Domain-specific projects should extend the controller with their own deterministic maintenance scripts, for example shard recovery, metric summarization, cache validation, or baseline launch checks. Keep those scripts project-local and call them from Codex cycles only when their preconditions are visible in `.research/`.

## Cross-Phase Memory

Long runs now use a generated memory layer instead of asking Codex to reread arbitrary old context. The design keeps the `claude-codex` file-backed state model and the local auto-research pattern of durable summaries, then adds a structured handoff bundle:

- `memory/handoff.md` is the first file the next cycle should read.
- `memory/phase_summaries.jsonl` condenses phase reports.
- `memory/artifact_index.json` shows active artifacts without indexing logs, progress feeds, generated memory, or cleanup archives.
- `memory/decision_memory.json` carries route decisions and phase history across jumps.
- `memory/risk_memory.json` keeps unresolved risks visible after phase changes.
- `memory/claim_memory.json` points writing stages back to claim/evidence artifacts.

The source of truth remains the phase report and artifact files. Generated memory can be refreshed with `paperfactory memory`; it should not be manually edited as the canonical record.
