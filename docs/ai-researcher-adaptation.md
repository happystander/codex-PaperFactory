# AI-Researcher Workflow Adaptation

This note records what PaperFactory borrows from
HKUDS/AI-Researcher and how it is adapted to the Codex plugin model.

## Borrowed Patterns

- Prepare before building: survey phases now require an inspected reference
  codebase matrix, not only a paper list.
- Ground ideas in code: method design must decompose the contribution into
  atomic academic concepts and map each concept to papers, code traces,
  implementation hooks, and falsifying ablations.
- Plan implementation explicitly: method design now requires a concrete
  data/model/training/testing plan before code or experiments expand.
- Smoke before escalation: method smoke tests require a runnable project
  manifest and a small low-budget run before longer training.
- Judge/refine loop: advanced comparison requires an implementation and
  protocol audit before expensive reproduction or checkpoint comparison.
- Analyze experiments before writing: paper evidence now requires an
  experiment-analysis note, so the paper draft cannot jump directly from raw
  metrics to claims.
- Section checkpoints: drafting starts from a claim-to-evidence map and
  proceeds section by section before final polishing.

## Deliberate Differences

PaperFactory does not import AI-Researcher's full Docker orchestration or
interactive cache prompts. Long runs here must stay resumable without blocking
on stdin, so the durable state remains `.research/state.json`, phase reports,
progress feed events, and file-backed artifacts.

Reference repositories are used as implementation evidence and design
inspiration. The final method should not directly depend on cloned research
repos unless the experiment explicitly records the dependency, license, version,
and protocol implications.

## New Required Artifacts

| Phase | Added artifact | Purpose |
| --- | --- | --- |
| `survey` | `literature/reference_codebases.md` | Select 5-8 useful repositories and record why they are reliable or excluded. |
| `data_sanity` | `data/benchmark_profile.md` | Fix dataset, baseline floor, comparison targets, metrics, and domain constraints. |
| `method_design` | `method/atomic_concepts.md` | Turn the proposed method into auditable units with math, paper, code, and ablation links. |
| `method_design` | `method/implementation_plan.md` | Specify data processing, model, training, testing, commands, and expected outputs. |
| `method_smoke` | `experiments/method_smoke/project_manifest.md` | Record the runnable minimal project layout and entry points. |
| `advanced_comparison` | `experiments/advanced_comparison/refinement_plan.md` | Save the judge/refine audit and repair plan before expensive comparisons. |
| `paper_evidence` | `results/experiment_analysis.md` | Explain gains, failures, confounders, and justified follow-up experiments. |
| `paper_drafting` | `paper/claim_evidence_map.md` | Ensure every paper claim points to an existing artifact before prose. |

## Practical Rule

AI-Researcher is strongest when it prevents an agent from skipping the boring
engineering checks. PaperFactory should keep that property: every attractive
claim needs a source, a runnable path, a metric, an ablation, or a documented
failure before it reaches the paper.
