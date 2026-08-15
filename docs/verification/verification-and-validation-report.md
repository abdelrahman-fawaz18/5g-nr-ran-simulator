# Verification and Validation Report

| Field | Value |
| --- | --- |
| Report version | 1.0 |
| Date | 2026-08-14 |
| Scope | Tier A static FR1 plus dynamic FR1 and bounded FR2-1 profiles |
| Method | ADR-0015 and the approved verification plan |
| Gate state | Passed locally and on cross-platform `main` CI |
| Calibration state | Not calibrated |

## 1. Executive conclusion

The verification program strengthens the simulator's evidence without changing its approved propagation,
link-adaptation, TBS, scheduling, KPI, dynamic-radio, experiment, or reporting equations. The
repository now has broad deterministic property tests, an implementation-independent integrated
link calculation, a centrally approved five-scenario semantic regression catalogue, a complete
Tier A/Tier B requirements evidence index, and a reproducible four-workload runtime/memory suite.

The correct portfolio claim is that the documented equations and tables are independently
verified within their declared domains and that the named small workloads meet explicit
engineering budgets. The project is **not** measurement-calibrated, a conformance simulator, a
real-time system, or a commercial RF-planning tool.

## 2. Evidence classification

| Component | Evidence | Result | Permitted interpretation |
| --- | --- | --- | --- |
| Release 18 propagation rows | Independent clarity-first equations plus retained vectors | E2 verified within documented domains | Matches pinned TR 38.901 equations to stated tolerances |
| NR resource, CQI, MCS, and TBS tables/procedure | Independently transcribed tables and integer calculator | E2 verified in supported one-layer domain | Matches pinned TS 38.104/38.211/38.214 inputs and procedure |
| Integrated link/noise/interference/SINR chain | Independent 50-digit Decimal oracle | E2 verified for representative vector | Reconstructs the analytical power chain within `1e-9` dB / `1e-12` relative tolerance |
| Kernel, queues, schedulers, KPIs, experiments | Hand vectors, invariants, replay, integration tests | E1 implemented with analytical verification where named | Implements the documented project contracts |
| Analytical SINR-to-CQI threshold | Formula, monotonic properties, sensitivity parameter | E1 uncalibrated | Reproducible analytical abstraction only |
| Dynamic shadow, handover, beams, blockage | Hand vectors, bounds, replay, regression | E1 implemented | Controlled sensitivity models only |
| Approved scenario digests | Five reviewed semantic baselines | Regression evidence | Detects unintended behavior changes; not an independent oracle |
| Runtime and memory | Reproducible named-workload benchmark | Engineering evidence | Meets the budgets below on the measured environment |
| Receiver/network measurements | No compatible approved dataset | No E3 evidence | No calibrated or real-network prediction claim |

## 3. Broad-domain and metamorphic verification

`tests/property/test_radio_and_scheduler_properties.py` uses Hypothesis 6.165.6 under the
repository-owned deterministic `engineering` profile. Each property runs 100 generated examples with
no wall-clock deadline and retains a reproducible failure representation.

The six property families establish that:

1. Cartesian link distance is symmetric, finite, and never below horizontal distance.
2. dBm/watt conversion round-trips and increasing transmit power cannot reduce linear power.
3. Thermal noise cannot decrease when bandwidth or receiver noise figure increases.
4. Allocation capacity cannot increase when additional link loss reduces SINR.
5. Allocation capacity cannot decrease when PRBs are added within the valid grid.
6. Round Robin, Max-C/I, and Proportional Fair always produce valid, positive, eligible,
   capacity-bounded PRB allocations across generated candidate sets.

These relationships test behavior without restating the production equations. Exact-domain,
boundary, conservation, statistical, replay, and failure tests from existing capability tests remain active.

## 4. Independent representative cross-check

Vector `RV-LINK-CHAIN-001` evaluates one serving link and two interferers over the exact
98.28 MHz transmission bandwidth of 273 PRBs at 30 kHz SCS. The independent oracle in
`tests/reference/independent_link_oracle.py` imports no production simulator module and uses
50-digit Decimal arithmetic.

| Quantity | Independent result |
| --- | ---: |
| Serving received power | -73 dBm |
| Thermal noise, NF 7 dB | -87.07534852191957 dBm |
| Aggregate interference | -86.87557397205660 dBm |
| SINR | 12.48536575271082 linear / 10.96401269319116 dB |

Production matches within `1e-9` dB and `1e-12` relative linear tolerance. This integrates the
project link-budget definition, versioned -174 dBm/Hz assumption, linear-power interference sum,
and SINR denominator. Separate radio-link and NR-capacity E2 suites remain the independent authority for
the propagation equations and NR capacity procedure.

## 5. Approved regression scenarios

`tests/regression/approved_scenarios.yaml` records inputs, seeds, replications, reviewed revisions,
expected digests, reviewer/date, included/excluded semantic fields, and regeneration commands.
It covers:

- static multi-cell radio state;
- static capacity inspection;
- integrated Tier A scheduler/queue/KPI execution;
- dynamic FR1 mobility/interference/handover execution;
- bounded FR2 beam/blockage/availability execution.

All comparisons are exact SHA-256 semantic matches. A future scientific-model change must receive
impact review and intentional baseline reapproval; updating a digest merely to silence a failure
is prohibited.

## 6. Requirements traceability

`consolidated-requirements-index.yaml` is the consolidated entrypoint. It inherits the seven prior
capability indexes and adds verification evidence, and is machine-checked against both requirements baselines.

| Requirement class | Count | Disposition |
| --- | ---: | --- |
| Mandatory Tier A (`SYS` through `OPS`) | 110 | Every ID maps to implementation/test evidence |
| Implemented Tier B dynamic (`DYN`) | 30 | Every ID maps to implementation/test evidence |
| Named deferred extension boundaries (`EXT`) | 5 | Explicitly excluded or narrowed; each effect on claims is recorded |

The five `EXT` rows were defined as boundaries rather than the system specification baseline implementation commitments.
Where the dynamic-radio layer implements a subset, the matrix states the remaining absent mechanism. No mandatory
Tier A or implemented Tier B requirement is silently uncovered.

## 7. Performance engineering

Profiling the dynamic FR1 workload before optimization recorded 148,480 calls in 0.058 s without
memory tracing. Semantic canonicalization was the largest necessary cost; repeated distribution
metadata discovery consumed about 0.011 s and performed redundant package-version lookups for
every run. The runtime now resolves an immutable process-wide dependency-version tuple once and
returns a fresh mapping to each caller. Scientific behavior is untouched, and all five approved
semantic digests remain exact.

The committed suite `benchmarks/performance-workloads.yaml` performs one warm-up and five measured
repetitions. Local results below use CPython 3.13.7 on Windows 11; runtime is the median and memory
is the maximum Python-managed `tracemalloc` peak.

| Workload | UEs | Intervals | Median | Peak MiB | Budget | Result |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Tier A static smoke | 2 | 12 | 0.0237 s | 0.462 | 1.0 s / 16 MiB | Pass |
| Dynamic FR1 smoke | 2 | 40 | 0.1061 s | 2.020 | 2.0 s / 32 MiB | Pass |
| Tier A static scale | 12 | 12 | 0.0771 s | 1.585 | 2.0 s / 32 MiB | Pass |
| FR2 availability smoke | 1 | 96 | 0.1339 s | 2.924 | 3.0 s / 48 MiB | Pass |

The exact command is:

```text
uv run python tools/benchmark_performance.py --repeat 5 \
  --output artifacts/performance/benchmark-local.json --force
```

Wall time varies with host load. `tracemalloc` excludes native allocations outside Python's
allocator. The budgets are conservative cross-platform regression guards for these named small
workloads, not scalability limits or real-time guarantees.

## 8. Assumptions and unresolved limitations

- Large-scale propagation follows the pinned outdoor scenario equations only inside their
  supported frequency, height, and distance domains.
- Antenna gains remain scalar in Tier A; the dynamic-radio layer FR2 beams are configured horizontal abstractions.
- No waveform, fast fading, HARQ, calibrated BLER curve, receiver implementation, or control-plane
  protocol stack is modeled.
- Dynamic shadow is correlated per link/trajectory, not through a spatially consistent map.
- Handover/availability logic is A3-inspired project behavior, not complete RRC/RLF behavior.
- Scheduler conclusions are valid only for paired, declared experiment scenarios and KPI
  populations; uncertainty intervals do not include model error.
- Performance results cover up to 12 UEs and 96 stored intervals in the named short workloads.

## 9. Release gate

The gate passed locally with 340 tests and 91.98% branch-aware coverage, then passed [GitHub
Actions run 31774034415](https://github.com/abdelrahman-fawaz18/5g-nr-ran-simulator/actions/runs/31774034415)
across Ubuntu/Windows × Python 3.11/3.13. Every matrix job ran formatting, lint, strict typing,
the full tests, the explicit performance smoke, security/dependency checks, build, isolated-wheel
execution, and the existing end-to-end CLI chain.
