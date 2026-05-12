---
name: data-availability
description: Prepare data/code availability statements, FAIR metadata checklists, repository plans, dataset citations, source-data packages, restricted-data wording, and reproducibility availability sections for academic manuscripts.
---

# Data Availability

Use this skill during `paper_evidence`, `paper_drafting`, or pre-submission packaging when a manuscript needs data/code availability, source data, repository planning, or reproducibility statements.

## Core Rule

Availability text links paper claims to inspectable evidence. Do not invent DOIs, accession numbers, repository names, licenses, embargo dates, ethics approvals, access committees, or data-use conditions.

## Sources Integrated

Condensed from local `nature-data` plus PaperFactory source-data manifest requirements.

## Workflow

1. Inventory every artifact supporting claims:
   - raw data;
   - processed data;
   - source data for figures;
   - model checkpoints;
   - code;
   - configuration files;
   - logs and seeds;
   - third-party datasets.
2. Classify access route:
   - public repository;
   - controlled access;
   - included in paper/supplement;
   - reused public source;
   - third-party restricted;
   - available on justified request;
   - not applicable.
3. Choose repository and identifier strategy before writing final prose.
4. Draft statements for data, code, models, and protocols separately unless target venue combines them.
5. Write `.research/paper/availability.md` and update `.research/figures/source_data_manifest.json`.

## Output Format

```markdown
# Availability Package

## Data Availability

## Code Availability

## Model/Checkpoint Availability

## Source Data For Figures

| Figure | Source file | Public location | Notes |

## Missing Information / Risk Flags
```

## FAIR Checklist

- stable identifier or repository path;
- license or access condition;
- version/date;
- provenance;
- schema/README;
- file format;
- relation to paper figures/tables;
- access restrictions and request route, if any.

## Red Lines

- Do not use vague "available upon request" unless a real restriction and access process are stated.
- Do not claim a repository upload exists before it does.
- Do not expose private paths in final manuscript text.
