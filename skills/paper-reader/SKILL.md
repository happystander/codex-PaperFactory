---
name: paper-reader
description: Build source-grounded reading notes from papers, PDFs, arXiv/Hugging Face paper pages, DOI pages, or pasted text, preserving claims, figures, tables, source anchors, and bilingual Chinese/English notes for later literature review and paper writing.
---

# Paper Reader

Use this skill when PaperFactory needs to read a paper deeply enough to support related work, baseline matrices, method comparison, or claim-level writing.

## Core Rule

Reading notes must be source-grounded. Preserve source anchors, figure/table evidence, method details, and limitations. Do not collapse a paper into vague bullet summaries when the result will support manuscript claims.

## Sources Integrated

Condensed from:

- `nature-reader`: full-paper Markdown reader, source maps, bilingual notes, figure proximity.
- `huggingface-papers`: Hugging Face/arXiv paper metadata and linked artifacts.
- `auto-research`: baseline-matrix and primary-source discipline.

## Workflow

1. Identify source type: PDF, arXiv/HF URL, DOI/publisher page, pasted text, or local notes.
2. Create stable anchors:
   - `S001`, `S002` for text blocks;
   - `F001` for figures;
   - `T001` for tables;
   - `C001` for captions or key claims.
3. Extract these fields:
   - task/problem;
   - method;
   - datasets and splits;
   - metrics;
   - baseline set;
   - claimed contribution;
   - reproducibility artifacts: code, checkpoint, data, project page;
   - limitations and failure cases.
4. Save under `.research/literature/readings/`:
   - `<slug>.md`;
   - optional `<slug>.json` for structured baseline facts.
5. Update `.research/literature/baseline_matrix.md` when the paper is a relevant baseline.

## Reading Note Format

```markdown
# Paper Reading: <Title>

- Source:
- Venue/date:
- Code/checkpoint/data:
- Task:
- Main claim:
- Nearest relation to our work:

## Method

## Experimental Protocol

## Results Worth Comparing

## What This Paper Does Not Show

## Reproduction Notes

## Claim Anchors
| ID | Source location | Claim | Evidence | Use in our paper |
```

## Bilingual Mode

If the user or project notes are Chinese, write short Chinese interpretation notes, but preserve titles, metric names, model names, equations, citations, and dataset names exactly.

## Red Lines

- Do not claim code/checkpoint availability without checking the official repo/model card.
- Do not treat a paper's abstract as enough evidence for a detailed baseline protocol.
- Do not paraphrase away limitations that affect fairness.
