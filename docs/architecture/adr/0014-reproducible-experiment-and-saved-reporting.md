# ADR-0014: Reproducible Experiment Design and Saved-Data Reporting

- **Status:** Accepted
- **Date:** 2026-08-14
- **Requirements:** KPI-011, EXP-001 through EXP-012, OPS-007

## Context

A deterministic single run is not a statistical experiment. Scheduler conclusions require
independent replications, common exogenous realizations, retained failures, uncertainty, and a
chain from every plot back to the actual run records. Live plotting or manually copied values
would break that chain. Parallel execution must not alter any run identity or random stream.

## Decision

- A strict versioned experiment manifest identifies the base scenario, scheduler set, optional
  Cartesian factors, timing inheritance, 128-bit master seed, explicit replication IDs,
  statistical method, selected KPI populations, failure policy, execution width, and output
  schema versions.
- Scheduler is a dedicated factor. Every non-scheduler factor is applied through a validated RFC
  6901 JSON Pointer before normal scenario validation. Normalized configuration collisions are
  rejected.
- One run identity covers the normalized scenario, all authored factor-level IDs, replication,
  model profiles, master seed, and code revision. Scheduler policies sharing the same remaining
  factors and replication must have one identical exogenous-configuration identity.
- Parallel workers own complete run-local model/RNG state. The experiment framework uses bounded,
  isolated thread workers; serial/parallel semantic equivalence is required. Any execution-engine
  change requires profiling and renewed equivalence evidence.
- Execution atomically promotes an experiment core containing the normalized design, all
  successful full run JSON artifacts, structured failed replications, completeness checks,
  checksums, and a versioned tidy replication dataset. Existing output directories are never
  overwritten.
- The experiment framework uses canonical JSON for the authoritative, portable metric dataset.
  Parquet remains an optional lossless scale optimization if profiling demonstrates a need; CSV is not an
  authoritative store.
- Analysis reloads and validates saved checksums, row digests, KPI definitions/units, null
  semantics, source-run files, completeness, and duplicates. It never receives a live simulation
  result.
- The declared v1 interval is a deterministic two-sided 95% nonparametric percentile bootstrap
  of replication means. Substantive studies use at least 2,000 resamples; the smoke profile uses
  500 for speed. Paired scheduler intervals bootstrap candidate-minus-reference differences
  matched by replication and every non-scheduler factor. Packet samples are never pooled as
  independent replications.
- SVG reporting reloads only the saved summary. Axes include zero, units and uncertainty are
  labeled, and the plot manifest records the summary checksum plus every plotted summary/source
  row ID. This format is directly consumable by downstream reporting.
- Execution-core files are immutable after the `COMPLETE` marker. Summary and plot namespaces are
  append-only derived artifacts; rerunning either into an existing namespace is rejected.

## Consequences

- A reviewer can trace a marker and confidence interval through summary IDs and tidy rows to the
  exact checked run JSON.
- Common-random-number comparisons reduce nuisance variation without coupling scheduler state.
- Bootstrap intervals are robust to an unproven normality assumption but do not remove the need
  for a sufficient replication count or precision review. A three-replication smoke result is
  verification evidence, not a publishable performance conclusion.
- JSON is larger than columnar storage, but minimizes installation and inspection friction at the
  current scale. The bundle schema permits a future format revision without changing simulations.
- Adding derived artifacts makes the experiment directory append-only rather than byte-immutable;
  the checksummed execution core itself never changes.

## Rejected alternatives

- One seed per policy: confounds policy effects with topology/channel/traffic variation.
- Construction-order seed spawning or a shared worker RNG: parallel/order-dependent results.
- A t interval by default: requires an unverified distributional suitability decision for
  each KPI and small sample.
- Plotting directly from returned Python objects: loses evidence provenance.
- CSV as the sole store: weak null/type/schema semantics.
- Silently skipping failed runs or missing KPIs: can bias conclusions.
