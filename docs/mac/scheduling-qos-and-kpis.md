# Scheduling, Queue Service, and KPI Pipeline

## 1. Capabilities

The scheduling pipeline integrates the verified static components into a time-domain RAN run:

```text
packet queues + serving SINR + available PRBs
        -> scheduler decision
        -> allocation-conditional TBS capacity
        -> one-slot packet service
        -> packet outcomes and KPI Contract 1.0 records
```

It implements Round Robin, Max-C/I, and Proportional Fair under one immutable observation and
explicit-decision interface. It does not add calibrated BLER, HARQ, fast fading, frequency-
selective scheduling, QoS priority inference, or load-coupled interference.

## 2. Slot sequence

At each configured normal-CP slot boundary `t`:

1. service reserved in the prior slot completes;
2. exact-tick deadlines expire after those completions;
3. packet arrivals stamped `t` enter their bearer queues;
4. each cell builds a read-only observation of associated UEs with positive queue payload;
5. the configured policy returns integer PRBs;
6. common invariants validate the decision;
7. the NR capacity model computes TBS capacity for each allocation;
8. existing queued packets are reserved oldest-arrival-first across a UE's bearers;
9. at `t + slot`, only reserved packet bits can complete;
10. the policy receives actual served-rate feedback and immutable interval/KPI records are built.

An arrival between boundaries waits for the next decision. An arrival exactly on a boundary is
eligible immediately. Reservation prevents a mid-slot arrival from consuming earlier service.

## 3. Policy definitions

### Round Robin (`round-robin-v1`)

For `P` available PRBs and `N` eligible UEs, every UE receives `floor(P/N)` PRBs. The first
`P mod N` UEs in the rotated order receive one extra PRB. A per-cell cursor advances by one UE
after every nonempty decision. Channel quality is not part of the rank.

### Max-C/I (`max-ci-v1`)

The rank is the NR capacity model full-cell-allocation transport payload under the UE's static serving SINR.
All PRBs go to the largest value; lexical UE ID breaks exact ties. This is the channel-efficiency
baseline and can starve weak UEs under sustained demand.

### Proportional Fair (`proportional-fair-v1`)

For eligible UE `i`:

```text
PF_i = full_allocation_rate_i / average_served_rate_i
average_next = (1 - alpha) * average_previous + alpha * realized_served_rate
```

The configured positive initial-rate floor initializes a newly observed UE. Every eligible UE is
updated after completion, including a zero served rate. Decimal state avoids hidden binary-
floating policy drift. The flat Tier A channel assigns the complete slot to the largest metric.

## 4. Conservation and waste

- Total per-cell allocation cannot exceed configured PRBs.
- Only associated UEs with nonempty queues are eligible.
- TBS capacity remains separate from reserved and actually served payload.
- Capacity beyond visible queue demand is unused.
- A reserved packet that expires before completion creates unused capacity rather than shifting
  its bits to a later arrival.
- Allocation with an outage/no-supported-MCS state carries zero capacity and remains explicit.
- Packet and bit ledgers from the deterministic mechanics layer reconcile after stop censoring.

`wasted_allocation_ratio` counts allocated PRB-slots whose UE carries zero queue payload at
completion. `unused_capacity_bits` additionally exposes partial waste inside a nonzero allocation.

## 5. Fair comparisons and randomness

The full configuration hash identifies each policy run. A separate
`exogenous_configuration_sha256` excludes the scheduler and human labels while retaining the
physical, traffic, timing, and model inputs used for randomness. Radio and traffic RNG streams use
that identity. Consequently, paired RR/Max-C/I/PF runs receive the same UE positions, LOS/shadow
draws, packet arrival times, and packet sizes.

Policy state is created per run and per cell. No state or RNG stream is shared between
replications.

## 6. KPI Contract 1.0 implementation

Every record contains metric name, definition version, base unit, aggregation level/ID,
population filter, measurement interval, sample count, run ID, value, explicit null reason, and
supporting arithmetic terms.

Implemented groups are bearer, UE, application profile, cell, and system where meaningful.
Metrics include:

- offered load, scheduled capacity, served throughput, and cohort goodput as distinct rates;
- median/P95/P99 queueing delay, service span, and system delay using type-7 quantiles;
- mean absolute successive system-delay variation per bearer;
- delivery, deadline-success/drop, overflow-drop, and censor ratios;
- fifth-percentile active-UE goodput and Jain fairness;
- served-payload spectral efficiency using actual `PRBs × 12 × SCS` bandwidth;
- PRB utilization, wasted-allocation ratio, and eligible-observation outage fraction.

`0` is a defined zero. `null` retains `insufficient_samples` or `zero_denominator`; dropped or
censored packets never receive invented delays.

## 7. CLI and result artifact

```powershell
uv run nr-ran-sim simulate examples/scenarios/scheduler-qos-smoke.yaml `
  --master-seed 0x11111111111111111111111111111111 `
  --replication-id 0 `
  --code-revision 1111111111111111111111111111111111111111 `
  --working-tree-state clean `
  --output artifacts/scheduler-simulation.json `
  --quiet
```

Use the actual Git revision for engineering results. The command requires an explicit clean/dirty
declaration rather than guessing provenance from an installed wheel.

The canonical JSON contains the normalized configuration identity, scheduler-neutral exogenous
identity, run identity, static radio snapshot, semantic trace, per-slot decisions/service, KPI
records, queues/packets, RNG registry, diagnostics, environment metadata, and a semantic digest.
Files are atomic and collision-safe unless `--force` is explicit.

## 8. Interpretation boundary

The simulator reports modeled scheduler-served payload and application-packet outcomes under the static,
analytical Tier A abstraction. It is not commercial throughput prediction. Full-buffer reuse-1
interference remains independent of actual cell activity; target BLER is metadata; there are no
PHY errors or retransmissions. Margin sensitivity and multi-replication confidence intervals are
required before a flagship conclusion.

Time-indexed decisions, queue service, and KPIs are available for saved evidence reporting.
Animated radio motion requires a time-varying radio profile.
