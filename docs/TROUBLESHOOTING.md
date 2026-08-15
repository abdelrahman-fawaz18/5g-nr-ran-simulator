# Troubleshooting

## `uv` selected the wrong Python

The supported range is 3.11–3.13. Select it explicitly:

```console
uv sync --frozen --all-extras --python 3.13
```

CI sets `UV_PYTHON` for each matrix interpreter. Do not regenerate the lock merely to work around
an unsupported local interpreter.

## Output already exists

Experiment bundles and derived summaries/plots are immutable by design. Choose a new output
directory. Do not delete or overwrite an evidence bundle that has already supported a claim.

## An experiment appears silent

`experiment-run` stages results atomically and prints completion only after the full design is
written. In the scheduler performance study, completed runs are streamed into a hidden staging directory so memory is
bounded by active workers. A missing final directory during execution is expected.

## Memory pressure during a large study

Use the current release, which bounds in-flight result objects and writes completed runs
immediately inside the atomic staging boundary. Reduce `--max-workers` if per-run native memory is
large on your host. Do not reduce replications after observing outcomes; create a new, explicitly
versioned experimental design instead.

## Summary or plot reports a digest mismatch

Treat this as evidence corruption, not a formatting problem. Run:

```console
uv run nr-ran-sim --error-format json experiment-verify PATH_TO_BUNDLE
```

Restore the exact artifact from its release asset or rerun the frozen manifest. Never edit a
metric row, summary, plot, checksum, or completion marker by hand.

## Portfolio visuals do not match the saved evidence

Run `uv run python tools/generate_portfolio_visuals.py`, then
`uv run pytest --no-cov tests/integration/test_portfolio_visuals.py`. The generated SVGs must match
the committed evidence-summary digest and deterministic file hashes. A numerical result change
requires a new verified evidence snapshot; the renderer is not an analysis editor.

## A KPI is `null`

Zero and undefined are different. Every `null` must have a machine-readable reason such as
`zero_denominator` or `insufficient_samples`. See the [KPI contract](requirements/kpi-contract.md)
before filtering or comparing it.

## Result interpretation is unclear

Start with the [model-fidelity contract](models/model-fidelity-contract.md). A verified equation is
not automatically a calibrated receiver/network model, and a scheduler result is valid only for
its declared scenario, traffic, queue, and policy implementation.
