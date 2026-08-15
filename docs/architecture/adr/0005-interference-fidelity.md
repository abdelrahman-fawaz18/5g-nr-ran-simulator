# ADR-0005: Tiered Interference Fidelity

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** LINK-003 through LINK-006; EXT-001

## Context

Ignoring interference limits realism, while activity-coupled per-PRB interference introduces cross-cell scheduling state before the kernel and policies are verified.

## Decision

Tier A contains two explicit profiles:

1. `noise-limited-v1`: interference power is zero.
2. `full-buffer-reuse1-v1`: every cochannel non-serving configured cell transmits across all PRBs at configured or deterministically derived PSD. When authoring supplies total cell power, normalization spreads it uniformly over the active transmission bandwidth and records the resulting PSD. Interference is deterministic for fixed geometry/propagation and is summed in linear power.

Tier B adds `activity-coupled-reuse1-v1`, where interference on a PRB depends on simultaneous neighbour allocation, transmit PSD, and active link state. It requires a separate ADR because it introduces multi-cell schedule coordination and potential fixed-point/timing choices.

## Consequences

- Tier A supports analytical checks and a pessimistic interference sensitivity without cross-cell scheduler coupling.
- Full-buffer results must not be described as observed neighbour load.
- Scheduler policies can be verified before interference feedback is introduced.
- Interference profile is mandatory result metadata; profiles cannot be pooled silently.

## Rejected alternatives

- Noise-limited only: insufficient sensitivity for a RAN portfolio study.
- Random interference margin: difficult to interpret and verify.
- Activity coupling in Tier A: excessive interaction risk before foundational validation.
