# ADR-0011: Resource, Capacity, and Inspection Boundary

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** LINK-007 through LINK-014; SYS-003, SYS-008

## Context

The NR capacity layer translates radio-link SINR into inspectable service capacity without pulling scheduler,
queue-service, BLER, or HARQ behavior forward. The proportional overhead input also has to become
an integer RE count before the TS 38.214 transport-block procedure can be applied.

## Decision

- A scheduling interval is one normal-CP slot: 14 symbols, 12 subcarriers per PRB, and the
  configured numerology's slot duration.
- Gross RE per PRB is 168. The configured non-data fraction is applied with
  `floor(168 * (1 - overhead))`; TS 38.214's 156-RE-per-PRB limit is then applied explicitly.
- The `analytical-awgn-gap-v1` CQI/MCS decision from ADR-0004 is evaluated from the serving-link
  SINR. CQI delay and filtering are omitted because the Tier A channel is static.
- TBS uses exact rational/integer arithmetic over the supported one-layer, one-codeword domain.
- Zero PRBs, zero data RE, below-CQI-1 outage, and CQI 1 without a compatible MCS Table 1 row
  produce named zero-capacity states. No fallback MCS is invented.
- `capacity-snapshot` evaluates each UE independently with all cell PRBs. This is a diagnostic
  ceiling for model inspection, not a simultaneous allocation and not summable cell throughput.
- The target error probability remains metadata. No 0.9 multiplier, BLER draw, retransmission,
  or HARQ process is added.

## Consequences

- Every capacity value can be reconstructed from exported PRBs, REs, CQI, MCS, TBS terms, and
  slot duration.
- The saved contract is immediately usable by static reporting without coupling presentation
  code into the model.
- The scheduler/KPI layer replaces the independent full-allocation context with explicit scheduler decisions
  before any served-throughput or utilization claim is made.
- A future exact DM-RS/control-symbol map or calibrated error model requires a new profile and
  regression review.

## Rejected alternatives

- Treat every one of the 168 REs as data: conflicts with the configured overhead contract and
  the TBS procedure's per-PRB limit.
- Multiply TBS by 0.9: confuses a target error design point with an observed success probability.
- Split PRBs equally in the snapshot: silently introduces a scheduling policy before the scheduler/KPI layer.
- Animate repeated static states: creates visual motion without modeled temporal behavior.
