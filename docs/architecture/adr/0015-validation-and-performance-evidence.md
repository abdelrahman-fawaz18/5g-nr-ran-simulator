# ADR-0015: Validation and Performance Evidence

- Status: Accepted
- Date: 2026-08-14
- Decision owners: Project owner and simulator maintainer
- Scope: Tier A static and Tier B dynamic profiles

## Context

The simulator has exact table fixtures, hand calculations, deterministic replay, and cross-platform
CI. The verification program broadens the exercised input domain, consolidates requirement
traceability, approve regression baselines, and quantify practical execution cost without
changing the approved scientific equations. It also avoids confusing
regression stability with independent verification or calibration.

## Decision

1. Property and metamorphic tests use Hypothesis with a repository-owned deterministic profile,
   fixed example budgets, no wall-clock deadline, and reproducible failure examples.
2. Independent numerical cross-checks live in `tests/reference/` and may use Python's `Decimal`
   arithmetic and independently transcribed constants, but may not import production radio
   equations or their intermediate results. Production and oracle paths meet only at assertions.
3. Approved reference scenarios are listed in one reviewed YAML catalogue. Each entry records the
   exact scenario, seed, replication, code revision used by the semantic identity, expected
   configuration/exogenous/result digests, approval date, reviewer, and regeneration command.
   These are regression oracles, not independent model-validation evidence.
4. A reproducible benchmark command measures named static and dynamic scenarios after one warm-up
   run. It reports the median wall time across measured repetitions and peak Python-managed memory
   from `tracemalloc`. Budgets are deliberately generous enough for supported Windows/Linux and
   CPython 3.11-3.13 runners. They are engineering guardrails, not real-time claims.
5. Optimizations require a recorded profile and exact semantic-regression checks. The verification program may
   remove redundant environment package-version discovery because profiling showed it on the
   critical path of every replication. Scientific equations, event ordering, schemas, and
   semantic digests remain frozen.
6. Calibration is not performed without a license-reviewed, independently sourced receiver or
   measurement dataset whose assumptions match the profile. The analytical SINR threshold,
   dynamic shadowing, beams, blockage, and handover abstractions therefore remain explicitly
   uncalibrated.

## Performance protocol

- Workloads: the approved static scheduler scenario, dynamic FR1, FR2, and an explicit
  12-UE static scaling scenario.
- Seed: `0x11111111111111111111111111111111`; replication: `0`.
- Warm-up: one unmeasured execution per workload.
- Runtime statistic: median `perf_counter_ns` elapsed time.
- Memory statistic: maximum `tracemalloc` peak over measured repetitions.
- Default local evidence: five repetitions per workload.
- CI smoke: one measured repetition with the same budgets.
- Runtime budgets: 2-UE static 1.0 s, 12-UE static 2.0 s, dynamic FR1 2.0 s, FR2 3.0 s.
- Python-managed peak-memory budgets: 2-UE static 16 MiB, 12-UE static 32 MiB, dynamic FR1
  32 MiB, FR2 48 MiB.

Machine load affects wall time, and `tracemalloc` excludes native allocations made outside
Python's allocator. The report must state both limitations. A future large-scale benchmark may
add process RSS and UE/slot scaling curves under a separately versioned protocol.

## Consequences

- Broad-domain failures become reproducible and shrink to inspectable examples.
- Recruiter-facing claims can link to an auditable distinction among E1 implementation, E2
  verification, regression stability, and the absent E3 calibration.
- Golden digests cannot be cited as independent correctness evidence.
- Performance changes that alter a semantic digest fail the approved-scenario gate.
- The benchmark demonstrates bounded usability for named small scenarios, not capacity planning,
  real-time operation, or production scalability.
