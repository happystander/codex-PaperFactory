# Codex PaperFactory 使用说明

这个插件把 `claude-codex` 的自动化流水线思想改造成 Codex 研究与论文生产流水线：用文件状态替代聊天上下文，用阶段门禁约束科研质量，用循环脚本支撑几天级别的无人值守运行，并在后期整合科研绘图和会议论文写作规范。

## 一次性启动

在你的研究项目目录运行：

```bash
/path/to/codex-PaperFactory/paperfactory new \
  --task "你的初始研究任务"

/path/to/codex-PaperFactory/paperfactory prompt
```

`new` 会同时创建 `.research/`、`.research/next_prompt.md` 和 `.research/dashboard.html`。然后让 Codex 使用 `autonomous-research` skill 执行生成的下一步提示。

日常查看状态和打开本地面板：

```bash
/path/to/codex-PaperFactory/paperfactory status --logs 8
/path/to/codex-PaperFactory/paperfactory dashboard --open
/path/to/codex-PaperFactory/paperfactory web --open
```

如果需要检查本机依赖：

```bash
/path/to/codex-PaperFactory/paperfactory doctor
```

更多 launcher 和 dashboard 细节见 `docs/local-ui.md`。

## 交互式 Web UI

启动本地控制台：

```bash
/path/to/codex-PaperFactory/paperfactory web --open
```

这个 UI 是本地 localhost 服务，不需要 Node，界面默认中文。它支持：

- 一键启动/暂停 Codex 长跑循环；
- 后台 detached 运行：网页或 Web UI 关掉后，已启动的后台任务仍继续跑；
- 明确显示是否还在运行、PID、最后活动时间、左侧文件树和上方阶段流程图；
- 可在附近 `.research/` 项目之间切换，每个研究任务保留自己的记忆配置；
- 从 `~/.codex/sessions` 读取 Codex 状态，显示短周期/长周期余量、重置时间、上下文窗口和 token 使用；
- 进展流来自 Codex 自己写入的 `.research/progress/feed.jsonl`，不生成伪进展，也不把原始日志按换行拆成聊天气泡；
- 可控制轮数、间隔和总运行时长；
- 可选择下一轮 prompt 读取哪些记忆：摘要、日志、人工介入、当前产物；
- 人工介入聊天：消息写入 `.research/human_interventions.md`，下一轮 prompt 自动带上；
- 编辑初始研究任务；
- 通过左侧文件树浏览 `.research/` 下的论文、报告、实验和日志产物，并在独立页面大预览文本、图片、SVG 和 PDF；
- 查看 `.research/figures/` 下的图表；
- 论文生成后在 `internal_review` 阶段自动运行“顶会审稿人”式内审，默认输出到 `.research/reviews/top_conference_review.md`。

注意：人工介入对下一轮生效。如果当前 `codex exec` 已经在运行，而你希望立刻改变方向，请先暂停后台任务，再发送介入并重新启动。

## 多天无人值守

```bash
/path/to/codex-PaperFactory/paperfactory run \
  --task "你的初始研究任务" \
  --until "2026-05-15 10:00:00" \
  --interval 1800
```

循环会周期性调用：

```bash
codex exec --full-auto --skip-git-repo-check "<phase prompt>"
```

所有状态、日志和产物都保存在 `.research/`。

## 阶段门禁

默认阶段如下：

1. `scope`: 明确研究问题、排除范围、数据集、指标、算力、成功标准。
2. `survey`: 查近期论文、官方代码、数据集、排行榜，建立 baseline matrix 和 novelty gap。
3. `data_sanity`: 检查真实数据、切分、标签、泄漏风险和指标协议。
4. `cheap_baselines`: 先跑强但便宜的基线。
5. `method_design`: 基于明确 gap 设计方法和可证伪消融。
6. `method_smoke`: 最小方法路径烟测。
7. `advanced_comparison`: 公平比较高级 baseline 或官方 checkpoint。
8. `paper_evidence`: 整理主结果、消融、鲁棒性、失败边界、复现信息，并用 `scientific-figure` 规划论文图，用 `drawio-academic-skills` 生成可编辑结构图 bundle 和 source-data manifest。
9. `paper_drafting`: 只基于已有证据写论文和 appendix，同时生成写作 issue 合同、LaTeX/BibTeX 源文件，并用 `conference-paper-writing` 与 `latex-paper-skills` 控制论文表达。
10. `internal_review`: 以审稿人视角检查创新性、证据、公平性、复现性和 LaTeX QA。

每个阶段必须写 `.research/reports/<phase>.json`。只有当 `status` 为 `complete` 且必需产物存在时，控制器才会推进到下一阶段。

## 科研绘图与论文写作

- `scientific-figure`: 在 `paper_evidence` 阶段规划论文图、source data、caption 和导出格式。
- `drawio-academic-skills`: 来自 `drawio-skills`，用于论文架构图、流程图、roadmap、方法图，默认保留 `.drawio + .spec.yaml + .arch.json + .svg` 可编辑 bundle。
- `conference-paper-writing`: 在 `paper_drafting` 和 `internal_review` 阶段把证据转成会议论文表述、表格、限制和复现说明。
- `paper-reader`: 在 `survey` 阶段做有 source anchor 的论文精读笔记。
- `citation-workflow`: 管理 BibTeX/Zotero 导出的文献库，做 claim-to-citation 支撑映射。
- `latex-typst-paper`: 检查 LaTeX/Typst 源码、引用、图表、伪代码、标签和投稿格式。
- `academic-polishing`: 中英文论文润色、翻译、标题摘要优化和去 AI 腔。
- `data-availability`: 写数据/代码/模型可用性声明、FAIR 元数据和 source data 清单。
- `manuscript-audit`: 做审稿人式内审、投稿 gate 和 revision roadmap。
- `reviewer-response`: 收到审稿意见后写逐点回复和修改清单。
- `presentation-deck`: 把论文或研究证据整理成组会/汇报/答辩用 storyboard。
- `paper-from-zero`: 来自 `latex-paper-skills`，做 topic brief、contribution map、evidence matrix 和综述/实证论文路由。
- `empirical-paper-writer`: 来自 `latex-paper-skills`，做实证论文的 issue 合同、结果状态和证据安全写作。
- `arxiv-paper-writer`: 来自 `latex-paper-skills`，做综述论文和 LaTeX/BibTeX/引用/编译脚本复用。
- `results-backfill`: 来自 `latex-paper-skills`，只用已验证实验结果回填占位符和升级结论。
- `latex-rhythm-refiner`: 来自 `latex-paper-skills`，在引用和数值稳定后做最终文本节奏润色。

快速生成一个指标图：

```bash
/path/to/codex-PaperFactory/paperfactory plot -- \
  --input metrics.csv \
  --x method \
  --y score \
  --output .research/figures/fig_main_metric \
  --formats svg,pdf
```

检索本地 BibTeX：

```bash
/path/to/codex-PaperFactory/paperfactory bib -- \
  --bib references.bib \
  --query "vision language recommendation" \
  --year-min 2022 \
  --has doi
```

检查论文初稿：

```bash
/path/to/codex-PaperFactory/paperfactory check -- paper/paper_draft.md --format markdown
/path/to/codex-PaperFactory/paperfactory check -- main.tex --format latex
```

## 关键原则

- 不编造引用、指标、表格或实验结果。
- proxy/smoke/diagnostic 结果不能当 final evidence。
- 只在证据门禁完成后写论文。
- 每个论文图都要有 source data、绘图脚本、caption 逻辑和 manifest。
- 比较协议不一致时必须标注为 diagnostic。
- 长跑任务中遇到 blocker，要写入 report 和 log，而不是静默跳过。
