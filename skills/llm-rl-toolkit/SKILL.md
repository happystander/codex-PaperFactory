---
name: llm-rl-toolkit
description: Use Open-LLM as a resource map and choose mature LLM fine-tuning, post-training, RLHF, preference-optimization, Agent/RAG, and evaluation frameworks before implementing anything from scratch. Apply when a task mentions LLMs, SFT, LoRA, DPO, PPO, GRPO, RLHF/RLAIF/RLVR, reward models, reasoning models, Agent training, RAG, verl, TRL, ms-swift, LLaMA-Factory, or OpenRLHF.
---

# LLM RL Toolkit

Use this skill when a research task involves LLM training, fine-tuning, alignment, post-training, RL for reasoning or agents, RAG, Agent frameworks, or LLM evaluation.

## Core Rule

Do not hand-roll training loops, preference optimizers, reward-model pipelines, distributed rollout systems, RAG stacks, Agent orchestration, or evaluation harnesses until you have checked the existing toolchain and written down why it is insufficient.

Use Open-LLM as a navigation map, then pick a maintained framework from official docs and local availability checks.

## References

- Open-LLM navigation map: `references/open_llm_map.md`
- LLM/RL framework selector: `references/rl_frameworks.md`

## Operating Loop

1. Classify the task: learning/reproduction, SFT/LoRA, preference optimization, RLHF/RLVR/GRPO, reward modeling, Agent/RAG application, evaluation, deployment, or paper writing.
2. Read the relevant reference section and choose a candidate framework before coding.
3. Check local availability with `paperfactory doctor`, then with minimal framework-specific commands.
4. Write a tool decision record before implementation:

```markdown
# LLM Tooling Decision

## Task Type
## Candidate Frameworks
## Selected Framework
## Why This Framework
## Local Availability Checks
## Data Format And License Constraints
## Reused Examples Or Configs
## Commands To Run
## Known Risks And Fallback
```

5. Put reusable commands/configs under `.research/experiments/` or the active experiment directory. Record metrics, checkpoints, model/data sources, and exact commands in the phase report.
6. If no framework fits, document the missing interface and implement the smallest adapter around an existing trainer instead of rewriting the whole pipeline.

## Default Framework Choices

- Hugging Face-native prototypes: prefer TRL for `SFTTrainer`, `DPOTrainer`, `GRPOTrainer`, `RLOOTrainer`, reward modeling, PEFT, Accelerate, DeepSpeed, and vLLM integrations.
- Large-scale distributed post-training: prefer verl for PPO/GRPO/DAPO-style RL, multi-GPU or cluster rollout/training separation, FSDP/Megatron backends, and vLLM/SGLang rollout engines.
- ModelScope/Qwen/multimodal full pipeline: prefer ms-swift for CPT/SFT/DPO/GRPO/PPO-style work, Web UI, inference, evaluation, quantization, deployment, and ModelScope datasets/models.
- Fast GUI/CLI fine-tuning: prefer LLaMA-Factory for quick SFT/RM/PPO/DPO/KTO/ORPO/SimPO recipes, LlamaBoard, and broad model template coverage.
- Ray/vLLM RLHF scripts: consider OpenRLHF when its launch scripts and scheduling model match the project better than verl or TRL.
- Agent/RAG applications: prefer LangGraph, LlamaIndex, Haystack, RAGFlow, Mem0, DSPy, or similar maintained frameworks from the Open-LLM map before custom orchestration.

## Minimal Checks

Run only the checks relevant to the selected framework:

```bash
python -c "import trl; print(trl.__version__)"
python -c "import swift; print('ms-swift import ok')"
python -c "import verl; print('verl import ok')"
swift --help
```

For verl, verify CUDA, backend, and image/source install constraints from official docs before launching multi-GPU jobs.

## Red Lines

- Do not invent framework support. Confirm with official docs, local imports, CLI help, or source examples.
- Do not treat Open-LLM as a ranking or scientific citation source. It is a resource map.
- Do not write paper claims from a training framework README; use papers, logs, metrics, and controlled experiments.
- Do not run RL on unverified rewards, mixed datasets, or unknown licenses without writing the risk.
- Do not implement PPO/DPO/GRPO/reward modeling from scratch unless the phase report explains why TRL, verl, ms-swift, LLaMA-Factory, and OpenRLHF do not fit.
