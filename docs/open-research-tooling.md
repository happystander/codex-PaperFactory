# Open Research Tooling

PaperFactory 的 skill 层已经覆盖科研任务拆解、文献阅读、引用管理、论文写作、图表、审稿和 rebuttal。真正还缺的是工具层：可检索、可解析、可追踪、可复现实验、可编译论文的开源工具。运行 `./paperfactory doctor` 可以看到当前机器上哪些工具可用。

## 当前建议

| 层级 | 推荐工具 | 作用 | PaperFactory 阶段 |
| --- | --- | --- | --- |
| 文献发现 | [arXiv API](https://info.arxiv.org/help/api/user-manual.html), [OpenAlex Works API](https://docs.openalex.org/api-entities/works/filter-works), [Crossref REST API](https://www.production.crossref.org/documentation/retrieve-metadata/rest-api/), [Semantic Scholar API](https://www.semanticscholar.org/product/api/tutorial) | 检索论文、扩展相关工作、获取 DOI/arXiv/venue/year/citation 元数据 | `survey`, `paper_drafting`, `internal_review` |
| 引用与元数据 | [Manubot](https://manubot.org/), `habanero`, `arxiv`, `semanticscholar` | DOI/arXiv/PMID 元数据补全、BibTeX/CSL 支持、引用一致性检查 | `survey`, `paper_drafting` |
| PDF 解析 | [GROBID](https://github.com/grobidOrg/grobid), `pdftotext`, `pypdf`, `pdfminer.six` | 从论文 PDF 中抽取标题、摘要、章节、参考文献和正文文本 | `survey`, `internal_review` |
| 论文构建 | `latexmk`, `pdflatex`, `bibtex`, `biber`, [Pandoc](https://pandoc.org/MANUAL.html), [Tectonic](https://tectonic-typesetting.github.io/en-US/) | 编译 LaTeX、转换 Markdown/LaTeX/DOCX、记录构建错误 | `paper_drafting`, `internal_review` |
| 数据与模型版本 | [DVC](https://www.dvc.org/), `git-lfs` | 数据集、checkpoint、模型权重和大文件版本控制 | `data_sanity`, `advanced_comparison` |
| 实验追踪 | [MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking) | 记录参数、指标、代码版本、artifact，并用 UI 比较实验 | `cheap_baselines`, `method_smoke`, `advanced_comparison` |
| 工作流复现 | [Snakemake](https://snakemake.github.io/), `make` | 把多步实验组织成可重跑的 DAG 或命令目标 | `cheap_baselines`, `method_smoke`, `advanced_comparison` |
| 配置管理 | [Hydra](https://hydra.cc/docs/intro/), `omegaconf` | 组合实验配置、命令行覆盖参数、避免脚本硬编码 | `data_sanity`, `method_smoke`, `advanced_comparison` |
| LLM 微调/对齐/RL | [TRL](https://huggingface.co/docs/trl), [verl](https://verl.readthedocs.io/), [ms-swift](https://github.com/modelscope/ms-swift), [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory), [OpenRLHF](https://openrlhf.readthedocs.io/) | SFT、LoRA、DPO、PPO、GRPO、reward model、推理部署、评测和分布式 rollout；先选框架再写自定义代码 | `survey`, `method_design`, `method_smoke`, `advanced_comparison` |

## 最小安装组合

如果只想把 PaperFactory 从“能写”升级到“能做可复现研究”，优先补这些：

```bash
pip install arxiv habanero semanticscholar pypdf pdfminer.six mlflow dvc snakemake hydra-core omegaconf
```

系统工具建议用系统包管理器或 conda/mamba 安装：

```bash
# names vary by Linux distribution or conda channel
pandoc latexmk biber poppler-utils git-lfs
```

GROBID 更适合单独部署成本地服务，或者用 `grobid_client` 连接已有服务。没有 GROBID 时，PaperFactory 会退回 `pdftotext` 或 Python PDF 包，但需要在报告里标明解析质量风险。

## Codex 使用规则

- `survey` 阶段优先使用 arXiv/OpenAlex/Crossref/Semantic Scholar 做文献发现和元数据交叉验证，原始 JSON/XML 缓存在 `.research/literature/api_cache/`。
- LLM/Agent/RAG/RL 任务要先用 `llm-rl-toolkit` 写 `.research/llm_tooling/tool_decision.md`，说明为什么选择 TRL、verl、ms-swift、LLaMA-Factory、OpenRLHF 或其他成熟框架。
- PDF 解析要记录工具、命令、输入文件和输出路径。GROBID 输出应保留 TEI/XML；`pdftotext` 输出应保留纯文本。
- 实验阶段优先把参数、指标、artifact 写入 MLflow；没有 MLflow 时必须写入 `.research/experiments/**/metrics.json` 和对应命令记录。
- 大文件不直接塞进 Git。优先 DVC 或 git-lfs；没有这些工具时写 checksummed manifest。
- 多步实验至少要有 Makefile 或 Snakemake 目标，避免只留下散乱命令。
- 论文阶段必须尝试可用的 LaTeX/BibTeX 构建工具，并把失败日志写入 `paper/latex_qa.md`。

## 取舍

这些工具不是每个任务都必须安装。PaperFactory 的原则是：工具可用就用工具提高证据质量；工具不可用就记录 fallback，不让一个可选依赖阻塞长期研究任务。
