# ADR-0012: Scheduler, Reserved Service, and KPI Pipeline

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** MAC-001 through MAC-011; KPI-001 through KPI-010; QOS-001 through QOS-010; EXP-002, EXP-003, EXP-006

## Context

The deterministic mechanics layer provides deterministic packets, queues, and externally injected
service grants. The radio-link layer provides a static serving-cell SINR. The NR capacity layer
calculates payload capacity for a caller-supplied PRB allocation. The scheduler/KPI layer connects
these boundaries without allowing scheduler policy to mutate
queues, alter exogenous randomness, serve packets that arrived after a scheduling boundary, or
turn allocation-conditional capacity into an unsupported PHY-success claim.

The Tier A radio profile is flat across the configured cell bandwidth. It has no per-PRB
frequency-selective channel state, BLER draw, HARQ, or load-coupled interference.

## Decision

- Scheduler policies consume an immutable per-cell observation containing the slot tick, PRB
  capacity, and lexically ordered eligible UEs with positive queue demand, static SINR, and
  full-allocation capacity. They return explicit positive integer PRBs per UE.
- A common validator rejects unknown/empty-queue UEs, duplicate/unsorted allocations,
  noninteger/nonpositive PRBs, and cell over-allocation before service reservations are created.
- Round Robin divides PRBs by quotient/remainder across eligible UEs and advances a per-cell
  cursor by one candidate each slot. The rotated order receives remainder PRBs first.
- Max-C/I assigns all PRBs to the UE with the largest full-allocation transport payload; exact
  ties use lexical UE ID.
- Proportional Fair assigns all PRBs to the largest
  `full_allocation_rate / exponentially_averaged_served_rate` metric. Decimal arithmetic retains
  the configured averaging coefficient and initialization floor. Eligible UEs with zero service
  receive a zero-rate EWMA update after slot completion; ties use lexical UE ID.
- Giving all PRBs to one Max-C/I/PF winner is the defined flat-channel Tier A baseline. A later
  frequency-selective profile requires per-PRB observations and a new policy version.
- Scheduling occurs only on complete slot boundaries. Warm-up end, measurement end, and drain
  end must align to the configured slot for the integrated Tier A runner.
- A decision at tick `t` reserves payload only from packets already queued at `t`. Reservation
  records each packet and first-service tick without removing bits. Completion at `t + slot`
  consumes only those records; intervening arrivals cannot use prior capacity. A packet expiring
  before completion makes its reserved portion unused. Completion exactly at deadline still wins
  through ADR-0001's event ordering.
- Capacity shared across multiple bearers of one UE follows oldest packet arrival, then lexical
  bearer/packet ID. This is QoS-neutral multiplexing, not 5QI priority inference.
- Scheduler-changing comparisons derive radio and traffic RNG streams from a versioned
  exogenous identity that includes timing, radio, models, topology, traffic, and extensions but
  excludes scheduler parameters and human labels. Full configuration identity still distinguishes
  the runs.
- KPI Contract 1.0 reducers consume immutable packet snapshots and completed scheduling-interval
  records. They do not mutate live simulation state. JSON records preserve definitions, units,
  aggregation, population, interval, sample counts, run identity, null reasons, and arithmetic
  terms.

## Consequences

- RR, Max-C/I, and PF see identical topology/channel/traffic draws in paired comparisons.
- PRB, packet, and bit conservation are independently checkable from the result artifact.
- First-service and completion ticks correctly represent a nonzero modeled service interval.
- Scheduler state and every allocation/service outcome are deterministic and serializable for
  downstream evidence reporting.
- Max-C/I and PF are intentionally extreme flat-channel baselines; conclusions cannot be
  generalized to frequency-selective production schedulers.
- Static full-buffer reuse-1 interference does not decrease when a cell has no allocation.
  Load-coupled interference remains the dynamic-radio layer.
- Cohort goodput can include drain completions, while served-throughput windows use completion
  events in the measurement interval, as required by KPI Contract 1.0.

## Rejected alternatives

- Seed RNG from the full scheduler-containing configuration: policy runs would see different
  users and packets.
- Apply capacity to the queue only at completion without reservation: mid-slot arrivals could
  consume service committed before they existed.
- Remove bits at scheduling time: queue occupancy and packet completion would occur too early.
- Use scheduled capacity instead of served rate for PF history: violates MAC-006 under sparse or
  deadline-limited demand.
- Infer 5QI priorities between bearers: exceeds the configured Tier A QoS contract.
- Add per-PRB frequency-selective scheduling without a channel model: creates unsupported detail.
