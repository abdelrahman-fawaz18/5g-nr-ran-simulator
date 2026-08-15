# Getting Started

## Install

Requirements: CPython 3.11–3.13 and Git. The project uses the pinned `uv` 0.12.3 workflow.

```console
python -m pip install uv==0.12.3
uv sync --frozen --all-extras
uv run nr-ran-sim --version
```

## Run the lightweight example

Validate the two-UE scheduler scenario, then execute one deterministic replication:

```console
uv run nr-ran-sim validate examples/scenarios/scheduler-qos-smoke.yaml --quiet
uv run nr-ran-sim simulate examples/scenarios/scheduler-qos-smoke.yaml \
  --master-seed 0x11111111111111111111111111111111 \
  --replication-id 0 \
  --code-revision 1111111111111111111111111111111111111111 \
  --working-tree-state clean \
  --output artifacts/quick-start.json \
  --quiet
```

On PowerShell, use the backtick as the line-continuation character or enter the command on one
line. The placeholder revision is suitable for a local smoke run; evidence runs should use
`git rev-parse HEAD` and an honestly recorded working-tree state.

## Run and verify a small paired study

```console
uv run nr-ran-sim experiment-run examples/experiments/scheduler-comparison-smoke.yaml \
  --output artifacts/paired-smoke \
  --code-revision 1111111111111111111111111111111111111111 \
  --working-tree-state clean
uv run nr-ran-sim experiment-summarize artifacts/paired-smoke
uv run nr-ran-sim experiment-plot artifacts/paired-smoke
uv run nr-ran-sim experiment-verify artifacts/paired-smoke
```

The verification command checks the completion marker, experiment and bundle digests, every run
file checksum, all replication-row lineage, summary lineage, plots, and scheduler seed pairing.

## Regenerate the recruiter-facing visuals

The committed charts are deterministic SVGs generated from the verified saved summary. The
renderer never runs the simulator or substitutes hand-entered values. Portfolio and experiment
figures share the `systems-lab-v1` design system: technical-gray canvas, navy structure, cobalt
primary data, steel comparison data, amber emphasis and green verification states.

```console
uv run python tools/generate_portfolio_visuals.py
uv run pytest --no-cov tests/integration/test_portfolio_visuals.py
```

`docs/assets/portfolio-visuals.json` records the source summary digest and each generated file hash.

## Reproduce the full flagship

The flagship is intentionally not a quick start: 360 source runs produced 2.63 GiB unpacked on the
recorded Windows/CPython 3.13 environment and execution took 13 minutes 49 seconds with eight
workers. Use the frozen manifest and a new output directory:

```console
uv run nr-ran-sim experiment-run examples/experiments/scheduler-performance-study.yaml \
  --output artifacts/scheduler-study-reproduction \
  --code-revision 6ef5c1dfdd773887060cf5af08c58de4cb4b8d96 \
  --working-tree-state clean
uv run nr-ran-sim experiment-summarize artifacts/scheduler-study-reproduction
uv run nr-ran-sim experiment-plot artifacts/scheduler-study-reproduction
uv run nr-ran-sim experiment-verify artifacts/scheduler-study-reproduction
```

See the [flagship protocol](experiments/scheduler-performance-study-protocol.md),
[experiment report](experiments/scheduler-performance-study-report.md), and
[troubleshooting guide](TROUBLESHOOTING.md) for interpretation and operational details.
