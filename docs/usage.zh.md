# Codex PaperFactory 使用说明

这个插件把 `claude-codex` 的自动化流水线思想改造成 Codex 研究与论文生产流水线：用文件状态替代聊天上下文，用阶段门禁约束科研质量，用循环脚本支撑几天级别的无人值守运行，并在后期整合科研绘图和会议论文写作规范。

## 一次性启动

在你的研究项目目录运行：

```bash
python /path/to/codex-PaperFactory/scripts/researchctl.py init \
  --task "你的初始研究任务"

python /path/to/codex-PaperFactory/scripts/researchctl.py next-prompt
```

然后让 Codex 使用 `autonomous-research` skill 执行输出的下一步提示。

## 多天无人值守

```bash
bash /path/to/codex-PaperFactory/scripts/autonomous_loop.sh \
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
8. `paper_evidence`: 整理主结果、消融、鲁棒性、失败边界、复现信息，并用 `scientific-figure` 规划论文图和 source-data manifest。
9. `paper_drafting`: 只基于已有证据写论文和 appendix，并用 `conference-paper-writing` 控制会议论文表达。
10. `internal_review`: 以审稿人视角检查创新性、证据、公平性和复现性。

每个阶段必须写 `.research/reports/<phase>.json`。只有当 `status` 为 `complete` 且必需产物存在时，控制器才会推进到下一阶段。

## 科研绘图与论文写作

- `scientific-figure`: 在 `paper_evidence` 阶段规划论文图、source data、caption 和导出格式。
- `conference-paper-writing`: 在 `paper_drafting` 和 `internal_review` 阶段把证据转成会议论文表述、表格、限制和复现说明。

快速生成一个指标图：

```bash
python /path/to/codex-PaperFactory/scripts/make_metric_plot.py \
  --input metrics.csv \
  --x method \
  --y score \
  --output .research/figures/fig_main_metric \
  --formats svg,pdf
```

## 关键原则

- 不编造引用、指标、表格或实验结果。
- proxy/smoke/diagnostic 结果不能当 final evidence。
- 只在证据门禁完成后写论文。
- 每个论文图都要有 source data、绘图脚本、caption 逻辑和 manifest。
- 比较协议不一致时必须标注为 diagnostic。
- 长跑任务中遇到 blocker，要写入 report 和 log，而不是静默跳过。
