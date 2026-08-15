# ADR-0013: Dynamic-Radio Causality, Handover, and FR2 Availability Boundary

- **Status:** Accepted
- **Date:** 2026-08-14
- **Requirements:** DYN-INT-001 through DYN-REP-003

## Context

Activity-coupled interference creates a circular dependency if every cell's current decision
depends on every other current decision. Mobility also requires a frozen order for position,
channel, measurement, association, and scheduling. FR2 adds beam/blockage vocabulary that can
easily imply unsupported array or protocol fidelity.

## Decision

- Preserve `tier-a-fr1-static-v1` and add opt-in `tier-b-fr1-dynamic-v1` and
  `tier-b-fr2-availability-v1` profiles.
- Use a one-slot causal interference lag. Slot `k` SINR uses neighbour PRB masks committed in
  slot `k-1`; slot zero uses a configured initial load. Allocations map to lowest contiguous PRBs.
- Update activity/SINR every slot. Update position, path loss, and correlated shadow only at the
  configured slot-aligned channel cadence, in ADR-0001 topology then link phases.
- Use per-link distance-driven Gauss-Markov shadow evolution with semantic RNG paths. Do not claim
  cross-link or map-consistent spatial correlation.
- Use deterministic linear motion with exact reflection at explicit bounds.
- Use an A3-inspired long-term-RSRP state machine with explicit offset, hysteresis, continuous
  time-to-trigger, interruption, deterministic ties, and ping-pong window. It is not an RRC
  procedure implementation.
- Use a separate availability-outage/recovery state with configured SINR thresholds/durations.
  It gates scheduling but is explicitly not NR radio-link failure or re-establishment.
- Limit FR2 to FR2-1 table/domain inputs, UMa/UMi large-scale path loss, a configured horizontal
  beam codebook using a declared parabolic pattern, and explicit `[start,end)` blockage losses.
- Store dynamic frames and transitions in the immutable simulation artifact; reporting remains a
  consumer of saved data.

## Consequences

- Cross-cell scheduling remains causal, deterministic, and independent of cell iteration order.
- Dynamic behavior is reconstructable and visualization-ready without duplicating model logic.
- The one-slot lag and low-index PRB placement are model assumptions that require sensitivity
  disclosure; they are not claims about a vendor scheduler.
- Large-scale mobility exposes association/interruption trade-offs but not fast-fading diversity.
- FR2 results are availability sensitivity cases, not array, blockage, beam-management, or field
  performance predictions.

## Rejected alternatives

- Same-slot sequential interference: cell declaration/order would change results.
- Undocumented fixed-point iteration: convergence and policy semantics would be ambiguous.
- Random interference margin: cannot reconstruct load or PRB overlap.
- Treat every channel update as an independent shadow draw: destroys spatial continuity.
- Call the outage state RLF: full NR monitoring/timer/re-establishment procedures are absent.
- Add a scalar “FR2 gain” without beam/blockage records: produces an impressive but unauditable
  number.
