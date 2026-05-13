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
   - `<slug>.json` for structured baseline and claim facts.
5. Update `.research/literature/claim_extraction.json` with one structured row per inspected paper.
6. Update `.research/literature/paper_priority_scores.json` when the paper changes the survey ranking.
7. Update `.research/literature/baseline_matrix.md` when the paper is a relevant baseline.

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

## Structured Claim Extraction

Each inspected paper should have a JSON row with:

```json
{
  "paper_id": "stable-slug-or-doi",
  "title": "",
  "year": 0,
  "venue": "",
  "source_url": "",
  "task": "",
  "method": "",
  "datasets": [],
  "metrics": [],
  "baselines": [],
  "limitations": [],
  "claims": [
    {
      "claim": "",
      "source_anchor": "S001",
      "evidence_anchor": "F001/T001/S002",
      "use_in_our_work": "baseline|motivation|contrast|not_applicable"
    }
  ],
  "artifacts": {
    "code": "",
    "checkpoint": "",
    "data": "",
    "project_page": ""
  }
}
```

## Paper Priority Scoring

When ranking candidate papers for survey depth, score each paper from 0 to 5 on:

- relevance to the current scoped task;
- recency;
- citation or community signal;
- code/checkpoint/data availability;
- protocol closeness: dataset, split, metrics, candidate set, prompt budget, inference constraints;
- baseline strength and whether it is a conceptual or reproducible SOTA.

Save the weighted ranking to `.research/literature/paper_priority_scores.json`. Include both included and excluded papers with a short reason.

## Bilingual Mode

If the user or project notes are Chinese, write short Chinese interpretation notes, but preserve titles, metric names, model names, equations, citations, and dataset names exactly.

## Red Lines

- Do not claim code/checkpoint availability without checking the official repo/model card.
- Do not treat a paper's abstract as enough evidence for a detailed baseline protocol.
- Do not paraphrase away limitations that affect fairness.
