# AI-Researcher Workflow Adaptation

This note records what PaperFactory borrows from
HKUDS/AI-Researcher and how it is adapted to the Codex plugin model.

## Borrowed Patterns

- Prepare before building: survey phases now require an inspected reference
  codebase matrix, paper priority scores, structured claim extraction, and
  code interface maps, not only a paper list.
- Ground ideas in code: method design must decompose the contribution into
  atomic academic concepts and map each concept to papers, code traces,
  implementation hooks, and falsifying ablations.
- Generate and criticize before committing: method design must produce multiple
  candidate methods, run a skeptical critic pass, and reject weak novelty before
  implementation.
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
| `survey` | `literature/paper_priority_scores.json` | Rank papers by relevance, recency, citation signal, code availability, protocol closeness, and baseline strength. |
| `survey` | `literature/claim_extraction.json` | Extract task, method, dataset, metric, baseline, limitation, and claim anchors into a machine-readable file. |
| `survey` | `literature/code_interface_map.md` | Map reference repos to data/model/training/evaluation/config interfaces and reusable modules. |
| `data_sanity` | `data/benchmark_profile.md` | Fix dataset, baseline candidates, comparison targets, metrics, and domain constraints. |
| `method_design` | `method/atomic_concepts.md` | Turn the proposed method into auditable units with math, paper, code, and ablation links. |
| `method_design` | `method/nearest_prior_diff.md` | Compare against the nearest three prior works at module level before claiming novelty. |
| `method_design` | `method/candidate_methods.json` | Generate multiple candidate methods with hypotheses, costs, overlaps, and falsifying ablations. |
| `method_design` | `method/idea_critic.md` | Record a top-conference-style critic pass that rejects weak candidates. |
| `method_design` | `method/novelty_risk.json` | Hard gate for smoke-test eligibility; high risk or missing falsification blocks advancement. |
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
