# Scheduler Performance Study Protocol

| Field | Frozen value |
| --- | --- |
| Protocol version | 1.1 |
| Status | Preregistered before execution; completed evidence published separately |
| Freeze date | 2026-08-14 |
| Experiment manifest | `examples/experiments/scheduler-performance-study.yaml` |
| Base scenario | `examples/scenarios/heterogeneous-qos-study.yaml` |
| Model profile | `tier-a-fr1-static-v1` |
| Statistical unit | One seeded replication |

This document freezes the question, design, hypotheses, and interpretation rules before the
flagship bundle is executed. Later results must not rewrite this protocol. Any post-result
analysis must be labeled exploratory.

Version 1.1 records a pre-result execution correction: the first attempt was stopped before bundle
publication when the orchestrator's retained in-memory results approached host memory pressure.
The runner now serializes completed runs into its existing atomic staging directory as they finish.
The question, scenario, variants, seeds, hypotheses, metrics, and statistical rules are unchanged;
the study will be rerun completely from the new clean revision.

## Question and engineering relevance

How do Round Robin, Max-C/I, and Proportional Fair scheduling trade aggregate efficiency, edge-user
service, and deadline-bearing application performance as broadband load increases in a mixed-traffic
FR1 macro deployment?

The comparison is useful because no scheduler dominates every objective. Max-C/I favors favorable
radio conditions, Round Robin divides resources without channel ranking, and Proportional Fair
uses an achievable-rate-to-historical-rate score. The study therefore exposes the engineering
choice between cell efficiency and service equity rather than presenting one universal winner.

## Fixed modeled system

- Three 3.5 GHz, 100 MHz UMa cells use the verified Release 18 path-loss implementation, static
  probability-drawn LOS state, independent static shadowing, and full-buffer reuse-one
  interference.
- Eight broadband UEs generate 12 kbit Poisson packets. Four low-latency UEs generate 2 kbit
  periodic packets every 1 ms with a 5 ms deadline.
- The warm-up, measurement, and drain windows are 20 ms, 200 ms, and 20 ms. The drain exceeds the
  deadline, so deadline-bearing measurement packets can reach a terminal outcome.
- The analytical SINR-to-CQI mapping is explicitly uncalibrated. Results describe this simulator
  profile and are not field-performance or protocol-conformance predictions.

## Experimental design

The factorial design contains three schedulers and four broadband load levels. Broadband mean
interarrival times are 4, 2, 1, and 0.5 ms; the low-latency stream remains fixed. Each of the 12
variants runs replications 0 through 29, for 360 expected runs.

Common random numbers pair topology, LOS/shadow state, and traffic draws across schedulers at each
load and replication. Scheduler is the target factor. Deployment, radio parameters, user counts,
traffic definitions, timing, seed plan, KPI definitions, and analysis method are controls.

Every estimate and scheduler difference uses the 30 replication values. The saved-data analysis
uses a deterministic 10,000-resample percentile bootstrap at 95% confidence. Max-C/I is the
predeclared comparison reference, and paired differences are `candidate minus Max-C/I`.

## Preregistered hypotheses

1. **Efficiency trade-off (H1).** At high or overload broadband load, Max-C/I will have higher
   system cohort goodput and payload spectral efficiency than at least one fairness-oriented
   scheduler. H1 is supported only when the paired candidate-minus-Max-C/I 95% interval is wholly
   below zero for the applicable metric.
2. **Deadline trade-off (H2).** At high or overload load, Round Robin or Proportional Fair will
   improve low-latency deadline-success ratio over Max-C/I. H2 is supported only when the paired
   95% interval is wholly above zero.
3. **Fairness trade-off (H3).** At high or overload load, Round Robin or Proportional Fair will
   improve Jain fairness or fifth-percentile UE goodput over Max-C/I. H3 is supported only when
   the paired 95% interval is wholly above zero.

An interval containing zero is reported as inconclusive; it is not converted into evidence for
"no effect." Effect sizes and interval widths are reported even when a hypothesis is unsupported.

## Primary and secondary outcomes

The primary outcomes are system cohort goodput, system payload spectral efficiency,
low-latency deadline-success ratio, system Jain fairness, and system fifth-percentile UE goodput.
Secondary diagnostic outcomes are system P95 delay, delivery ratio, PRB utilization, and
application-level goodput, P95 delay, and delivery ratio. Secondary outcomes explain behavior but
cannot rescue an unsupported primary hypothesis.

## Acceptance and stop rules

The study is eligible for conclusions only if all of these checks pass:

- exactly 360 runs succeed, with no missing or duplicate run identities;
- all 120 scheduler-pairing groups pass the exogenous-identity check;
- every primary estimate and paired comparison has 30 valid replication values/pairs and no null
  value;
- the bundle, replication dataset, summary, and plot checksums validate through the saved-data
  pipeline;
- the recorded code revision is clean and contains this protocol plus the memory-bounded execution
  correction documented in protocol version 1.1;
- no model, manifest, KPI definition, exclusion, or seed is changed after observing results.

There is no early stopping. Failed execution is repaired only for an implementation defect that
would invalidate every affected run; such a change requires a new protocol version and complete
rerun. An unexpected but valid result is retained.

## Publication outputs

The report will show the five primary outcomes across load with 95% intervals, paired effect
tables against Max-C/I, the complete-result checks, and a short limitations section. Static
evidence views read only a derived, checksum-linked view of the frozen summary. They do not recompute or
silently filter the scientific results.
