---
name: scientific-runtime-tooling
description: Use when a research task depends on scientific computing CLIs, simulation packages, HPC jobs, or domain runtimes such as GROMACS, LAMMPS, OpenFOAM, Quantum ESPRESSO, bioinformatics tools, CFD, molecular dynamics, DFT/DFPT, or other official toolchains. Guides Codex to use official docs or ScholarAIO toolref first, record provenance, run smoke tests, and avoid guessing parameters.
---

# Scientific Runtime Tooling

Use this skill when PaperFactory has to run or adapt real scientific software rather than only write ML scripts.

## Core Rule

Do not invent command flags, force fields, solvers, pseudopotentials, parameters, or validation criteria from memory. Use official documentation or a local tool reference first, then record the exact provenance. A successful command is not automatically a scientifically valid result.

See `references/scientific_toolref_patterns.md` for the condensed ScholarAIO scientific-runtime and tool-onboarding patterns.

## Operating Workflow

1. Identify the scientific layer: molecular dynamics, CFD, quantum/DFT, bioinformatics, data conversion, visualization, or HPC orchestration.
2. Check the runtime:
   - binary path and version;
   - MPI/GPU/OpenMP/CUDA support when relevant;
   - available examples or test data;
   - license, hardware, and queue constraints.
3. Look up tool behavior through `scholaraio toolref search/show` when available. If not available, use official docs, official repository manuals, or bundled examples and record the fallback.
4. Use the research library workflow to find parameter, dataset, protocol, and validation references before scaling an experiment.
5. Run a minimal smoke test before any long job.
6. Preserve input files, commands, configs, environment, stdout/stderr summary, output checksums, and metric extraction scripts.
7. Compare outputs against literature, official examples, conservation checks, sanity plots, or known benchmark ranges.
8. Register every paper claim in `.research/evidence/registry.json` with command provenance and metric source.

## Runtime Provenance Contract

For every scientific tool run that matters, write:

- `.research/experiments/<phase>/runtime_provenance.md`
- `.research/experiments/<phase>/commands.sh`
- `.research/experiments/<phase>/metrics.json` when metrics exist
- `.research/experiments/<phase>/failure_notes.md` when a run fails or is scientifically invalid

`runtime_provenance.md` should include tool name, version, binary path, docs/source used, input files, parameters that matter scientifically, command, hardware, runtime, output paths, validation checks, and limitations.

## Escalation Rules

- If an official example fails, stop and diagnose install/environment before changing scientific assumptions.
- If a parameter source is missing, do not silently choose a plausible value; mark it as a blocker or diagnostic assumption.
- If a smoke run uses reduced system size, lower cutoff, fewer steps, proxy input, or CPU-only fallback, label results as diagnostic.
- Long runs should enter `.research/queue/tasks.jsonl` with timeout, retry budget, expected output, dependencies, and stop condition.
- Clean temporary or failed scratch files after preserving the evidence needed to understand the run.
