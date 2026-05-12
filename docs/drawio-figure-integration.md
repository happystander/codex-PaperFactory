# Draw.io Figure Integration

PaperFactory integrates `bahayonghang/drawio-skills` through the installed
`drawio-academic-skills` skill. Use it for architecture figures, workflow
figures, roadmaps, ablation pipelines, method diagrams, formula-safe diagrams,
and paper-ready technical illustrations.

## Installed Skill

The academic Draw.io skill is installed at:

```text
~/.codex/skills/drawio-academic-skills
```

The default offline workflow creates an editable bundle:

- `<name>.drawio`
- `<name>.spec.yaml`
- `<name>.arch.json`
- `<name>.svg`

PNG, PDF, JPG, and embedded `.drawio.svg` exports require draw.io Desktop. If
Desktop is unavailable, Codex should still deliver the editable bundle and SVG,
then record the unavailable export clearly.

## PaperFactory Contract

During `paper_evidence`, Codex must produce:

- `.research/figures/diagram_plan.md`
- `.research/figures/drawio_bundle_manifest.json`

The manifest should include each diagram's purpose, figure type, source bundle,
export path, caption intent, validation command, and any missing Desktop-only
export.

## Recommended Figure Types

- `architecture`: method modules, model pipeline, system/data flow.
- `workflow`: research pipeline, experiment loop, evaluation protocol.
- `roadmap`: staged method development, ablation schedule, long-horizon plan.

Use `academic` or `academic-color` themes by default. Labels should be readable
at paper scale, and color must not be the only carrier of meaning.

## Useful Commands

```bash
node ~/.codex/skills/drawio-academic-skills/scripts/cli.js input.yaml output.svg --validate --write-sidecars --strict-warnings
node ~/.codex/skills/drawio-academic-skills/scripts/cli.js input.yaml output.drawio --validate --write-sidecars
node ~/.codex/skills/drawio-academic-skills/scripts/runtime/diagrams-net-url.js output.drawio
```

Source: https://github.com/bahayonghang/drawio-skills
