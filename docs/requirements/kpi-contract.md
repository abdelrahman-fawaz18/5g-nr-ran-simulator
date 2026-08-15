# KPI Contract

| Field | Value |
| --- | --- |
| Definition version | 1.0 |
| Applies to | Tier A metrics and later compatible extensions |
| Time basis | Integer simulation ticks converted to SI seconds for rates |

## 1. Observation windows and packet cohorts

Let `t_w` be warm-up end, `t_m` measurement end, `t_d` drain end, and `T = t_m - t_w` in seconds.

- Traffic generated before `t_w` affects queue and scheduler state but is excluded from the measurement cohort.
- Measurement-cohort packets have arrival ticks in `[t_w, t_m)`.
- No traffic is generated in `[t_m, t_d]`.
- Time-window rate metrics use events occurring in `[t_w, t_m)` unless stated otherwise.
- Cohort metrics follow measurement-cohort packets until completion, terminal drop, or `t_d`.
- A cohort packet unresolved at `t_d` is `censored`; it remains in denominators where the contract says all cohort arrivals.
- Every aggregate reports population and sample/censor counts.

## 2. Rate and load metrics

| KPI | Formula | Population and notes |
| --- | --- | --- |
| Offered load | `sum(payload_bits of arrivals in [t_w,t_m)) / T` | Report per bearer/UE/class/cell/system. |
| Scheduled capacity | `sum(transport-block payload capacity committed in [t_w,t_m)) / T` | Capacity offered by the PHY abstraction, whether or not queues use it. |
| Served throughput | `sum(unique queue payload bits removed by service in [t_w,t_m)) / T` | Excludes control/overhead and duplicated/retransmitted bits. |
| Cohort goodput | `sum(payload_bits of cohort packets completed by t_d) / T` | A completion after `t_m` may contribute because drain resolves the cohort; label explicitly as cohort goodput. |
| Fifth-percentile UE goodput | Type-7 empirical 5th percentile of per-UE cohort goodput | Population: active UEs with positive offered load; report `n`. |

Rates use bit/s. Decimal prefixes are used for display (`1 Mbit/s = 10^6 bit/s`), while machine data remains in base units.

## 3. Packet delay metrics

For a completed packet `p`:

- queueing delay: `first_service_tick(p) - arrival_tick(p)`;
- service span: `completion_tick(p) - first_service_tick(p)`;
- system delay: `completion_tick(p) - arrival_tick(p)`.

A packet with all payload served in one slot still has a service span equal to the modeled service interval; it is not forced to zero. A packet completing exactly at its deadline is on time.

Median, P95, and P99 use the Hyndman–Fan type-7 empirical quantile over completed measurement-cohort packets. Each output reports completed count and censored count. Dropped/censored packets do not receive artificial delay values; their effect is shown through delivery/deadline ratios and censor counts.

## 4. Jitter

For one bearer’s completed cohort packets ordered by completion time, with system delays `D_1 … D_n`:

`jitter = (1 / (n - 1)) × sum(|D_i - D_(i-1)| for i=2…n)`.

Jitter is undefined, not zero, for `n < 2`. System-level jitter is not computed by mixing packets from unrelated bearers; aggregate reporting summarizes per-bearer jitter with population statistics.

## 5. Packet outcome ratios

| KPI | Numerator | Denominator |
| --- | --- | --- |
| Delivery ratio | Cohort packets completed by `t_d` | All cohort arrivals |
| Deadline-success ratio | Deadline-bearing cohort packets completed at or before deadline | All deadline-bearing cohort arrivals |
| Overflow-drop ratio | Cohort packets terminally dropped by queue overflow | All cohort arrivals |
| Deadline-drop ratio | Cohort packets terminally expired | All deadline-bearing cohort arrivals |
| Censor ratio | Cohort packets unresolved at `t_d` | All cohort arrivals |

Ratios are undefined when their denominator is zero. Terminal causes are mutually exclusive. A later calibrated PHY profile may add PHY-failure ratios without redefining existing causes.

## 6. Fairness

For per-UE cohort goodputs `x_i` over `n` active UEs with positive offered load:

`J = (sum(x_i)^2) / (n × sum(x_i^2))`.

The result is undefined for `n = 0` or when all `x_i = 0`; it is `1` for one active UE with positive goodput. Report the UE population and offered-load filter with every value.

## 7. Spectral efficiency and resource use

The transmission bandwidth is `B_tx = N_RB × 12 × SCS_hz`, not nominal channel bandwidth.

| KPI | Formula |
| --- | --- |
| Cell payload spectral efficiency | `served payload bits in [t_w,t_m) / (T × B_tx)` |
| PRB utilization | `allocated PRB-slots / available PRB-slots` |
| Wasted-allocation ratio | `allocated PRB-slots carrying zero queue payload / allocated PRB-slots` |

PRB ratios are undefined when the denominator is zero and must lie in `[0,1]` otherwise. A future multi-layer metric must introduce a new definition version rather than silently multiplying the Tier A formula.

## 8. Interference and coverage diagnostics

Tier A reports distributions rather than a single opaque coverage label:

- serving received power in dBm;
- interference power in dBm, or explicit absence in noise-limited mode;
- noise power in dBm;
- SINR in dB;
- outage fraction: scheduling observations for which no supported CQI/MCS threshold is met divided by eligible observations.

Outage in this contract is a link-abstraction state, not radio-link failure as defined by the complete NR protocol stack.

## 9. Replication aggregation

- Preserve every replication value.
- Default confidence level: 95%.
- Single-policy mean intervals use Student’s t interval when the sample is approximately suitable; otherwise report a deterministic bootstrap percentile interval with method, resample count, and bootstrap seed.
- Policy comparisons use paired replication differences with shared exogenous streams; confidence intervals are computed on those differences.
- Never pool packet samples across replications and treat them as independent replications.
- Failed replications are reported and excluded only under the experiment’s predeclared failure policy.

## 10. Machine-readable null semantics

- `0`: the KPI is defined and its measured value is zero.
- `null` plus reason `insufficient_samples`: the definition requires more observations.
- `null` plus reason `zero_denominator`: a ratio/rate denominator is zero.
- `null` plus reason `not_applicable`: the active model profile does not define the KPI.
- `null` plus reason `run_failed`: the replication did not produce a valid metric.
