# ADR-0003: Semantic, Order-Independent RNG Streams

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** QOS-005, EXP-002 through EXP-004, EXP-007

## Context

Sequential RNG consumption couples unrelated components: adding a UE or logging draw can change every later result. Calling `SeedSequence.spawn()` in construction order has a similar order-dependence risk. Scheduler comparisons require identical exogenous randomness.

## Decision

- The experiment manifest carries a 128-bit hexadecimal master seed and integer replication ID.
- The deterministic mechanics layer pins NumPy and uses `numpy.random.Generator` with `PCG64DXSM`.
- Every stream has a semantic path, for example `topology/ue-group-A/position`, `link/cell-1/ue-7/los`, or `traffic/ue-7/bearer-1/interarrival`.
- Derive seed material from SHA-256 over a canonical byte encoding of baseline ID, master seed, replication ID, and semantic path; split the digest into fixed-width unsigned words for `SeedSequence`.
- Never use Python’s process-randomized `hash()` and never rely on call-order spawning.
- One generator instance has one owner and is not shared across parallel workers.
- Exogenous paths are unchanged across scheduler policies. Policy-specific randomness adds a `policy/<policy-id>/...` namespace.
- Run metadata records engine, NumPy version, semantic paths, and nonsecret derived fingerprints.

## Consequences

- Adding an unrelated component does not perturb existing streams.
- Comparative policies receive paired topology, channel, and traffic realizations.
- Changing path names is a numerical behavior change and requires a model-profile version bump.
- Exact reproduction is guaranteed only for the pinned RNG engine/library environment; manifests still preserve sufficient provenance for diagnosis elsewhere.

## Rejected alternatives

- Global `random`/`numpy.random` state: hidden coupling.
- One generator per run: consumption-order coupling.
- Construction-order `spawn()`: topology refactors change streams.
- OS entropy per worker: irreproducible experiments.
