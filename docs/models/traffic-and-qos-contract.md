# Traffic and QoS Contract

## 1. Scope

Traffic is modeled at application-payload packet level. The simulator does not model IP/TCP behavior, PDCP/RLC segmentation, core-network delay, admission control, or a full 5QI enforcement pipeline. A bearer is a simulation queue and policy context, not a claim that a standards-complete QoS Flow exists.

## 2. Tier A source primitives

| Source | Parameters | Semantics |
| --- | --- | --- |
| Periodic | initial offset, interval | One arrival every exact interval; useful for control/telemetry. |
| Poisson | mean rate or mean inter-arrival | Exponential inter-arrival draws from the bearer traffic RNG stream. |
| Bounded uniform | minimum and maximum inter-arrival | Independent continuous draws, quantized to integer ticks by the documented half-to-even rule. |

Packet size is either constant or discrete bounded-uniform in integer bits. Bounds are inclusive. Invalid zero/negative sizes or intervals fail validation.

## 3. Queue contract

- One FIFO per bearer.
- Packet identity survives partial service.
- Capacity may be bounded by packet count, bit count, or both.
- A new packet that would violate either limit is tail-dropped as one whole packet.
- Partial service never reorders packets.
- Deadline is relative to arrival and must be positive when present.
- Completion at the exact deadline succeeds; any unfinished packet is expired immediately afterward.
- Terminal causes are `completed`, `overflow_drop`, `deadline_expired`, `phy_failure` when a future profile supports it, and `censored_at_stop`.

## 4. Application profiles

Application profiles are named configuration objects, not code branches. The repository may ship examples such as:

| Example profile | Intended study role | Recommended source family | QoS emphasis |
| --- | --- | --- | --- |
| `broadband_stream` | eMBB-like sustained load | Periodic or Poisson, larger packets | Goodput and fairness |
| `command_control` | Small, frequent control messages | Periodic or bounded uniform | Tail delay and deadline success |
| `detection_telemetry` | Sparse sensor/detection reports | Periodic or Poisson | Delivery and resource efficiency |

The names do not imply a validated traffic model for a commercial service. Exact rates, packet sizes, deadlines, and queue limits are experiment inputs and must be justified in the experiment report.

## 5. 5QI metadata boundary

3GPP TS 23.501 defines 5QI as a reference to QoS characteristics that influence access-node treatment. The simulator may store an optional `qos_reference_5qi` and citation for comparison, but it shall not silently copy or infer priority, packet delay budget, packet error rate, averaging window, GBR, AMBR, or core-network behavior.

If an experiment intentionally uses a standardized 5QI row, every adopted field must be copied into explicit simulation parameters, cite TS 23.501 V18.12.0 Table 5.7.4-1, and state which portions of the end-to-end QoS behavior remain unmodeled.

## 6. RNG and comparison behavior

Each bearer owns independent semantic streams for inter-arrival and packet-size draws. Adding an unrelated bearer must not perturb another bearer’s generated sequence. Scheduler comparisons reuse the same traffic stream identities so policies see identical arrivals and sizes.

## 7. Warm-up, measurement, and drain

- Warm-up traffic builds representative queue/scheduler state but is excluded from the cohort.
- Measurement arrivals define the cohort.
- Sources stop at measurement end.
- Drain resolves cohort outcomes without injecting new work.
- Drain duration must be at least the maximum configured packet deadline when deadline-success conclusions are reported, or the experiment must disclose the resulting censoring.

## 8. Verification obligations

- exact sequences for periodic sources;
- seeded replay for all stochastic sources;
- distribution mean/quantile sanity checks with predeclared statistical tolerances;
- same-tick multi-packet preservation;
- FIFO and bit-conservation invariants under partial service;
- exact overflow/deadline boundary fixtures;
- stream-independence perturbation tests;
- cohort and drain accounting tests.
