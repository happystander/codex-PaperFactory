# LLM And RL Framework Selector

Sources inspected on 2026-05-13:

- TRL docs: https://huggingface.co/docs/trl
- TRL installation: https://huggingface.co/docs/trl/installation
- verl docs: https://verl.readthedocs.io/
- verl GitHub: https://github.com/verl-project/verl
- ms-swift GitHub: https://github.com/modelscope/ms-swift
- LLaMA-Factory GitHub: https://github.com/hiyouga/LLaMA-Factory
- OpenRLHF docs: https://openrlhf.readthedocs.io/

## Decision Matrix

| Framework | Prefer When | Avoid When | First Checks |
| --- | --- | --- | --- |
| TRL | Hugging Face-native SFT, DPO, GRPO, RLOO, reward modeling, PPO experiments, PEFT/Accelerate/DeepSpeed/vLLM integration. Best for prototypes and clean trainer APIs. | Need large cluster orchestration, complex rollout/training placement, or non-HF model infrastructure. | `uv pip install trl`; `python -c "import trl; print(trl.__version__)"` |
| verl | Large-scale RL post-training, reasoning RL, PPO/GRPO/DAPO-style algorithms, FSDP/Megatron training, vLLM/SGLang rollouts, multi-GPU or multi-node jobs. | Single-GPU quick SFT/DPO is enough, or the environment cannot satisfy CUDA/backend constraints. | Prefer official Docker or source install; check CUDA/backend; `python -c "import verl"` |
| ms-swift | ModelScope/Qwen-heavy projects, text or multimodal full pipeline, CPT/SFT/DPO/GRPO/PPO-style work, Web UI, evaluation, quantization, deployment. | Need a minimal HF-only codebase or a framework-independent algorithm prototype. | `pip install ms-swift -U`; `swift --help`; `python -c "import swift"` |
| LLaMA-Factory | Fast code-light SFT/RM/PPO/DPO/KTO/ORPO/SimPO recipes, LlamaBoard GUI, broad model templates, quick reproduction or teaching demos. | The method requires deep custom trainer internals or distributed rollout research. | Clone/install official repo; try CLI/Web UI examples and matching model template. |
| OpenRLHF | Ray + vLLM RLHF launch scripts, scalable RLHF, agentic RL, PPO/DAPO/REINFORCE++ style recipes where its scheduler matches the job. | Existing verl or TRL scripts already cover the needed dataflow more simply. | Check official docs/examples; verify Ray, vLLM, DeepSpeed, and GPU placement. |

## Method Mapping

| Need | Start Here | Notes |
| --- | --- | --- |
| SFT or LoRA fine-tuning | ms-swift, LLaMA-Factory, TRL | Pick ms-swift for ModelScope/full pipeline, LLaMA-Factory for GUI/recipe speed, TRL for HF trainer integration. |
| DPO or offline preference optimization | TRL, ms-swift, LLaMA-Factory | Prefer official dataset formats and trainer examples. |
| Reward model training | TRL, ms-swift, LLaMA-Factory | Record preference data source, annotator/model policy, and label quality. |
| PPO/GRPO/RLOO/DAPO reasoning RL | verl, ms-swift, TRL, OpenRLHF | Prefer verl/ms-swift/OpenRLHF for multi-GPU rollout-heavy work; TRL for smaller HF-native experiments. |
| RL with verifiable rewards | verl, ms-swift, OpenRLHF | Keep reward code audited, deterministic where possible, and logged with test cases. |
| Agent or tool-use RL | verl agentic RL, OpenRLHF, LangGraph plus evaluation harness | Separate environment state, tool traces, reward logic, and model training logs. |
| Multimodal alignment/RL | ms-swift, verl, LLaMA-Factory | Confirm model family and processor/template support before launch. |
| Evaluation | lm-evaluation-harness, RAGAS, DeepEval, promptfoo, EvalScope, OpenCompass | Use task-appropriate metrics and preserve raw outputs. |

## Required Tool Decision Record

Before implementing a trainer or experiment, write `.research/llm_tooling/tool_decision.md`:

```markdown
# LLM Tooling Decision

## Task Type
SFT / DPO / GRPO / PPO / reward modeling / Agent RL / RAG / evaluation / deployment.

## Constraints
Model, dataset, license, GPUs, CUDA, distributed backend, time budget, privacy, expected outputs.

## Candidates
| Framework | Fit | Missing Pieces | Local Status |

## Selected Framework
Why this framework beats the alternatives for this phase.

## Reuse Plan
Official examples, configs, data converters, reward functions, adapters, and evaluation commands.

## Fallback
What to do if installation, GPU memory, dataset format, or trainer support fails.
```

## Implementation Rules

- Reuse official trainer/config entry points. Modify data converters, reward functions, model adapters, or config files before modifying framework internals.
- If a framework example is copied into the project, keep the upstream URL, commit/tag, license, and local modifications in the report.
- Keep rewards and metrics auditable. Add small reward-function unit tests before long RL runs.
- Separate smoke tests from long runs. A smoke test should use a tiny dataset slice and small max steps.
- Keep checkpoints and large logs out of Git; use DVC/git-lfs or checksummed manifests.

## No-Reinventing-Wheels Checklist

Before custom code is allowed, answer all questions:

- Which framework was checked first, and what exact command or source file proves it was insufficient?
- Is the missing piece just a dataset converter, reward function, config, callback, or adapter?
- Can the method be expressed as a TRL Trainer, verl reward/rollout loop, ms-swift CLI config, LLaMA-Factory recipe, or OpenRLHF launch script?
- Does the proposed custom code affect scientific novelty, or is it only infrastructure?
- How will the custom path be tested against an official example?
