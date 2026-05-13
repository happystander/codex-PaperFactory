# Open-LLM Map For PaperFactory

Source: https://github.com/chengyuZou/Open-LLM, inspected on 2026-05-13.

Open-LLM is a Chinese/English navigation repository for LLM, Agent, RAG, multimodal learning, and engineering resources. Its README states that resources are organized by direction rather than ranked. Treat it as a map for "what to check first", not as evidence for a paper.

## How To Use It

Use this map during `survey`, `method_design`, `method_smoke`, and `advanced_comparison` when the research task touches LLMs, agents, RAG, multimodal systems, or alignment.

1. Identify the task family.
2. Pick official repositories or docs from the relevant family.
3. Inspect maintenance, examples, license, and whether the interface matches this project.
4. Convert useful repositories into `literature/code_interface_map.md`.
5. Convert useful papers or docs into source-grounded notes with `paper-reader` and `citation-workflow`.

## Task Families

| Family | Open-LLM Coverage | PaperFactory Use |
| --- | --- | --- |
| LLM theory and foundations | ML/DL foundations, Transformer/NLP, LLM surveys, RL foundations | Build prerequisite reading lists and background notes. |
| From-scratch LLM reproduction | MiniMind, transformer code walkthroughs, hands-on LLM courses | Use for educational reproduction only; do not use as a production trainer. |
| Fine-tuning | LLaMA-Factory, self-LLM, Chinese LLM lists, ModelScope tutorials | Prefer mature fine-tuning stacks before custom scripts. |
| Agent frameworks | LangGraph, AutoGen, CrewAI, LlamaIndex, Haystack, DSPy | Use existing orchestration/memory/tool-call patterns before custom agent loops. |
| RAG and Agentic RAG | RAGFlow, LlamaIndex, Haystack, RAG technique collections, RAG-Anything | Use for retrieval pipelines, multi-modal RAG, and evaluation baselines. |
| Memory | Mem0 and lifelong-agent resource lists | Use existing memory abstractions before custom vector/log stores. |
| Code agents | OpenHands, MetaGPT, OpenManus, code-agent projects | Use as implementation references or baselines for software-engineering agents. |
| Workflow/application platforms | Dify, FastGPT, Coze, LangChain-Chatchat | Use for product-style prototypes and UI/workflow comparisons. |
| Evaluation and tracing | RAGAS, DeepEval, promptfoo, OpenAI Evals, lm-evaluation-harness, LangSmith, Phoenix, Weave | Use for metrics, regression checks, traces, and evaluation harnesses. |
| Multimodal and vertical domains | OCR, speech, Chinese/domain models | Check domain-specific baselines and data/model constraints. |
| Tool ecosystem | PyTorch, Hugging Face, ModelScope, LangChain, MCP, IDEs, compute/API platforms | Pick stable infrastructure rather than ad hoc glue. |

## Phase Guidance

### Survey

- Use Open-LLM to seed candidate frameworks and reference repositories.
- Record each selected repo in `literature/code_interface_map.md` with data entry, model entry, training command, evaluation command, config system, reusable modules, and incompatibilities.
- Do not include every link. Select repositories that are maintained, documented, licensed, and relevant to the protocol.

### Method Design

- Use nearest-prior and framework checks to avoid novelty claims that are only "framework X plus parameter tuning".
- If the proposed method is a trainer, loss, rollout algorithm, reward function, retrieval flow, or agent planner, first compare it against the closest framework implementation.

### Experiments

- Prefer official examples/configs as the first smoke path.
- Keep local modifications as small patches, adapters, reward functions, data converters, or config files.
- Record exact versions, commit hashes when cloned, and commands.

### Paper Writing

- Cite original papers and project papers, not Open-LLM itself, unless discussing resource curation.
- Use framework docs only for reproducibility details and implementation provenance.

## Selection Filters

Keep a resource only if at least one is true:

- It provides an official implementation for a target baseline.
- It exposes reusable data/model/training/evaluation interfaces.
- It is a maintained framework that avoids writing custom infrastructure.
- It provides an evaluation, tracing, or deployment component required by the experiment.

Reject or de-prioritize a resource if:

- It is only a list of links with no direct role in the task.
- It has no license, no examples, or unclear maintenance.
- It forces a protocol change that would make comparisons unfair.
