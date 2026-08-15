# Scheduler Performance Study Report

| Field | Value |
| --- | --- |
| Report version | 1.0 |
| Study | `scheduler-performance-study` |
| Protocol | [Preregistered protocol 1.1](scheduler-performance-study-protocol.md) |
| Execution revision | `6ef5c1dfdd773887060cf5af08c58de4cb4b8d96` (clean) |
| Design | 3 schedulers × 4 loads × 30 paired replications |
| Result | 360/360 runs complete; 120/120 pairing groups pass |
| Model claim | Verified, 3GPP-informed project model; not calibrated |

## Executive result

The study supports the preregistered deadline and fairness trade-offs. Under overload, Round Robin
and Proportional Fair each improved low-latency deadline success and edge-user goodput relative to
Max-C/I with paired 95% intervals excluding zero. Max-C/I retained a narrow spectral-efficiency
advantage over Proportional Fair at overload, which supports H1 only for that comparison.

Round Robin produced the highest aggregate goodput in this particular bursty, finite-queue model.
That result is important precisely because it prevents a simplistic "Max-C/I always maximizes
throughput" story. The modeled Max-C/I policy assigns a full slot to one eligible UE and does not
redistribute unused transport-block capacity within the slot; Round Robin divides PRBs among
eligible queues. The result is therefore a scheduler/queue/resource interaction inside this
declared model—not a general claim about deployed networks.

## Question, variables, and controls

The research question asks how Round Robin, Max-C/I, and Proportional Fair trade aggregate
efficiency, deadline-bearing traffic performance, and service equity as broadband load rises.

- **Target factor:** scheduler policy.
- **Swept control:** broadband Poisson mean interarrival of 4, 2, 1, or 0.5 ms.
- **Fixed traffic:** four UEs produce 2 kbit packets every 1 ms with a 5 ms deadline.
- **Fixed radio scene:** three 3.5 GHz, 100 MHz UMa cells, full-buffer reuse-one interference,
  static LOS/shadow state per replication, eight broadband UEs, and four low-latency UEs.
- **Pairing:** common random numbers preserve each replication's topology, radio state, and traffic
  draws across scheduler policies.
- **Uncertainty:** deterministic 10,000-resample percentile-bootstrap 95% intervals over the 30
  replication values; policy effects are paired candidate-minus-Max-C/I differences.

## Preregistered hypothesis decisions

| Hypothesis | Decision | Decisive evidence |
| --- | --- | --- |
| H1: Max-C/I efficiency advantage at high/overload load | Supported narrowly, not universally | At overload, Proportional Fair minus Max-C/I spectral efficiency was `-0.0396 bit/s/Hz`, 95% CI `[-0.0681, -0.0116]`; goodput was inconclusive and Round Robin was higher |
| H2: fairness-oriented policy improves low-latency deadline success | Supported | At overload, Round Robin minus Max-C/I was `+0.517`, CI `[+0.424, +0.605]`; Proportional Fair was `+0.482`, CI `[+0.398, +0.571]` |
| H3: fairness-oriented policy improves Jain fairness or edge goodput | Supported | At overload, Round Robin improved Jain fairness by `+0.178`, CI `[+0.151, +0.204]`, and fifth-percentile UE goodput by `+1.927 Mbit/s`, CI `[+1.843, +1.994]` |

No interval containing zero was reinterpreted as proof of no effect. Secondary metrics explain the
observed mechanisms but do not change the preregistered decisions.

## Overload operating point

Means below are across 30 replications. Full confidence intervals remain in the committed summary
and generated evidence charts.

| Scheduler | System goodput | Low-latency deadline success | Jain fairness | 5th-percentile UE goodput | Payload spectral efficiency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Round Robin | 190.594 Mbit/s | 100.0% | 0.709 | 2.000 Mbit/s | 0.638 bit/s/Hz |
| Proportional Fair | 137.187 Mbit/s | 96.5% | 0.585 | 1.496 Mbit/s | 0.356 bit/s/Hz |
| Max-C/I | 141.714 Mbit/s | 48.3% | 0.531 | 0.073 Mbit/s | 0.396 bit/s/Hz |

Selected evidence-backed plots:

- [Low-latency deadline success](../../evidence/scheduler-study-v1/plots/deadline_success_ratio--application--low-latency-ad4187ad.svg)
- [System goodput](../../evidence/scheduler-study-v1/plots/cohort_goodput_bps--system--system-0dc8cd0a.svg)
- [Jain fairness](../../evidence/scheduler-study-v1/plots/jain_fairness--system--system-0dc8cd0a.svg)
- [Fifth-percentile UE goodput](../../evidence/scheduler-study-v1/plots/fifth_percentile_ue_goodput_bps--system--system-0dc8cd0a.svg)
- [Payload spectral efficiency](../../evidence/scheduler-study-v1/plots/payload_spectral_efficiency_bit_per_s_per_hz--system--system-0dc8cd0a.svg)

## Acceptance and integrity

All preregistered acceptance checks passed:

- 360 expected runs, 360 successful, zero failed/missing/duplicate IDs;
- 120 common-random-number pairing groups, zero violations;
- every primary estimate and paired comparison contains 30 valid values/pairs;
- 5,040 replication rows, 168 estimates, 112 paired differences, and 14 plots passed checksum
  and source-lineage verification;
- the experiment ran from a clean committed revision;
- the scientific design, seeds, metrics, exclusions, and hypotheses were not changed after result
  observation.

The full bundle semantic digest is
`0cd57c3b9155bcba6a3e58b26882620e24bd2c82aa1c9e9232a3b411fe666c04`. The compact source-control
snapshot is [evidence/scheduler-study-v1](../../evidence/scheduler-study-v1); its manifest links
back to that bundle. The complete 2.63 GiB unpacked bundle is distributed with the private release,
not committed as ordinary source.

## Limitations

- Intervals quantify replication uncertainty inside this simulator, not receiver/model error or
  real-network uncertainty.
- The analytical SINR-to-CQI mapping is not measurement-calibrated; there is no HARQ, fast fading,
  waveform, control plane, or complete 5G QoS scheduler.
- Max-C/I, Round Robin, and Proportional Fair are the exact documented project policies. Their
  queue-service behavior must not be generalized to vendor schedulers with different allocation,
  retransmission, or QoS logic.
- The scenario is static FR1 UMa with scalar antenna gains and full-buffer interference. It does
  not establish the same ordering under mobility, spatial consistency, MIMO, FR2, or field load.
- The first execution attempt was stopped before publication due to an orchestration memory
  bottleneck. Protocol 1.1 records the memory-bounded correction; the accepted study was rerun in
  full from a clean revision.
