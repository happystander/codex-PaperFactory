# Scientific Toolref Patterns From ScholarAIO

Source inspected: <https://github.com/ZimoLiao/scholaraio/tree/main> on 2026-05-13.

ScholarAIO separates general scientific runtime behavior from tool-specific skills. PaperFactory adopts that separation:

- `scientific-runtime-tooling` defines the runtime contract.
- Task-specific knowledge should come from official docs, local tool references, project examples, and papers.
- A future tool-specific PaperFactory skill should stay lightweight and point to tool references instead of becoming a copied manual.

## Shared Runtime Protocol

1. Identify the scientific tool and subtool.
2. Query local tool references first when available.
3. Fall back to official documentation when local coverage is partial.
4. Validate the installed binary and a minimal example before running a research experiment.
5. Record command, version, input, output, and validation evidence.
6. Separate "the command ran" from "the result is scientifically meaningful".

Anti-patterns to avoid:

- dumping remembered command flags without checking docs;
- changing parameters only to make a run pass;
- hiding failed runs that explain scientific risk;
- treating reduced diagnostic runs as final comparisons;
- letting generated files clutter the research folder after evidence has been preserved.

## Tool Onboarding Pattern

When adding a new scientific tool:

1. Choose official sources first: documentation site, official repository docs, manuals, or bundled examples.
2. Decide whether to fetch a stable source tree or maintain a small manifest of selected docs.
3. Build a minimal index with page/program/section names.
4. Test fetch, list, show, and search behavior before relying on it in research.
5. Create a lightweight skill that says how to use the tool reference, not a long copied manual.
6. Add smoke tests and update PaperFactory doctor checks only for binaries or packages that are broadly useful.

## Domain Patterns

| Domain | What to verify before trusting results |
| --- | --- |
| Molecular dynamics / GROMACS | force field source, topology generation, units, timestep, ensemble, equilibration, energy drift, temperature/pressure stability, analysis command provenance. |
| LAMMPS-style simulations | units, atom style, pair style, potential file source, boundary conditions, timestep, thermo output, neighbor settings, and reproducible input script. |
| OpenFOAM / CFD | solver choice, mesh quality, boundary conditions, turbulence model, residual criteria, physical units, time-step/Courant behavior, and post-processing command. |
| Quantum ESPRESSO / DFT | pseudopotential source, functional, cutoff, k-point mesh, smearing, convergence thresholds, SCF convergence, and comparison target. |
| Bioinformatics | reference genome/database version, index build command, sample metadata, tool version, random seeds, quality filters, and statistical test assumptions. |

## PaperFactory Integration

- `data_sanity`: record dataset/reference/database versions and scientific constraints.
- `method_design`: reject methods whose scientific parameters or validation criteria cannot be sourced.
- `method_smoke`: run the smallest valid tool path and write runtime provenance.
- `advanced_comparison`: scale only after smoke validity and protocol matching are clear.
- `paper_evidence`: expose scientific assumptions and diagnostic limitations in the evidence registry.
