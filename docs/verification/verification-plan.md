# Verification Plan

| Field | Value |
| --- | --- |
| Plan version | 1.0 |
| Status | Active |
| Requirements baseline | `../requirements/system-requirements.md` version 1.0 |
| Model profile | `tier-a-fr1-static-v1` |
| Principle | Verify observable requirements with independent oracles and explicit tolerances |

## 1. Verification objectives

The verification program must establish that:

1. configuration fails closed and preserves dimensional meaning;
2. simulation time, event order, queues, bits, and PRBs obey invariants;
3. every standard-derived table/equation matches an independent reference;
4. stochastic components are reproducible and statistically plausible;
5. scheduler policies match their definitions under controlled fixtures;
6. metrics match versioned formulas and censoring rules;
7. experiment execution is order/parallelism independent;
8. no result or claim exceeds the active model profile’s evidence level.

## 2. Verification layers

| Layer | Marker | Purpose | Execution |
| --- | --- | --- | --- |
| Static quality | `quality` | Formatting, lint, typing, imports, dependency/security checks | Every commit/PR |
| Unit | `unit` | Local behavior, tables, units, queue arithmetic | Every commit/PR |
| Reference | `reference` | Equations/tables against independent values | Every commit touching a model; full CI |
| Invariant/property | `property` | Broad input domains and impossible-state detection | Every PR; deterministic seed |
| Integration | `integration` | Component interactions and lifecycle | Every PR |
| Reproducibility | `reproducibility` | Same identity produces same semantic outputs | Every PR and release |
| Statistical | `statistical` | Generator properties and analysis methods | Scheduled/full CI; bounded false-positive policy |
| Regression | `regression` | Approved small scenarios and schema compatibility | Every PR after baseline approval |
| Performance | `performance` | Runtime/memory budgets without behavior change | Scheduled/release; smoke threshold on PR |
| Documentation/claims | `docs` | Links, traceability, evidence wording | Every PR/release |

## 3. Independence and oracle rules

An oracle is independent when it does not call the production symbol, reuse its generated intermediate output, or merely restate the same code in a test helper.

Approved oracle classes:

- exact values transcribed from a pinned standards table and reviewed against the versioned PDF;
- a hand-worked analytical calculation with retained derivation;
- a small, separately implemented reference calculation optimized for clarity rather than reuse;
- comparison against an identified independent simulator/tool under matched assumptions;
- invariants and metamorphic relationships that do not require the same formula.

Self-generated snapshots alone are regression evidence, not independent verification.

## 4. Reference-vector catalogue

The vector IDs are frozen before production implementation. Numeric worksheets/source fixtures live in `tests/reference/data/` and include source/version/reviewer metadata.

### 4.1 Time, numerology, and resources

| Vector | Inputs | Expected | Source | Tolerance |
| --- | --- | --- | --- | --- |
| RV-NUM-001 | SCS 15 kHz, normal CP | μ=0, 1 slot/ms, 14 symbols/slot, slot=1 ms | TS 38.211 Tables 4.2-1 and 4.3.2-1 | Exact |
| RV-NUM-002 | SCS 30 kHz, normal CP | μ=1, 2 slots/ms, 14 symbols/slot, slot=0.5 ms | Same | Exact |
| RV-NUM-003 | SCS 60 kHz, normal CP | μ=2, 4 slots/ms, 14 symbols/slot, slot=0.25 ms | Same | Exact |
| RV-RB-001 | 20 MHz, 15 kHz | 106 PRBs | TS 38.104 Table 5.3.2-1 | Exact |
| RV-RB-002 | 100 MHz, 30 kHz | 273 PRBs | Same | Exact |
| RV-RB-003 | 100 MHz, 60 kHz | 135 PRBs | Same | Exact |
| RV-RB-004 | 100 MHz, 15 kHz | Invalid/N/A | Same | Exact failure |
| RV-BW-001 | 273 PRBs, 30 kHz | `273 × 12 × 30 kHz = 98.28 MHz` transmission bandwidth | TS 38.211 §4.4.4.1 plus arithmetic | Exact integer Hz |

The implementation test shall cover the entire FR1 table, not only the representative rows above.

### 4.2 Geometry and event semantics

| Vector | Inputs | Expected | Tolerance |
| --- | --- | --- | --- |
| RV-GEO-001 | `(0,0,25)` to `(300,400,1.5)` m | 2D=500 m; 3D=`sqrt(500²+23.5²)` m | 1e-12 relative |
| RV-EVT-001 | completion and deadline at tick 100 | completion terminal cause; no deadline drop | Exact event sequence |
| RV-EVT-002 | two arrivals same bearer/tick | two unique FIFO packets | Exact |
| RV-EVT-003 | arrivals at slot boundary and one tick later | first eligible now, second next boundary | Exact |
| RV-EVT-004 | permuted entity declaration order | same semantic trace digest | Exact semantic digest |
| RV-QUEUE-001 | 1000-bit packet, service 300/400/300 bits | completion after third interval, zero remainder | Exact integer bits |
| RV-QUEUE-002 | full queue plus new packet | whole new packet tail-dropped | Exact terminal cause |

### 4.3 Link budget

| Vector | Inputs | Expected | Tolerance |
| --- | --- | --- | --- |
| RV-LB-001 | Tx 46 dBm, Gtx 15 dBi, Grx 0 dBi, path loss 130 dB, misc loss 2 dB | Rx = −71 dBm | 1e-12 dB |
| RV-NOISE-001 | 20 MHz, NF 7 dB, density −174 dBm/Hz | −93.989700043 dBm | 1e-9 dB |
| RV-NOISE-002 | 100 MHz, NF 7 dB | −87 dBm | 1e-12 dB |
| RV-INT-001 | two interferers each −90 dBm | aggregate −86.989700043 dBm | 1e-9 dB |
| RV-SINR-001 | S=−80 dBm, I=−90 dBm, N=−100 dBm | Linear ratio `10^(-8)/(10^(-9)+10^(-10))`, result ≈9.586073148 dB | 1e-9 dB |
| RV-LA-001 | SINR exactly at an analytical MCS threshold | that MCS is eligible | Exact boundary policy |
| RV-LA-002 | SINR one representable value below lowest threshold | outage, not fallback MCS | Exact |
| RV-LA-003 | increasing SINR over threshold sweep | selected MCS never decreases | Property |

The temperature/density constant is a versioned project assumption, not attributed to 3GPP.

### 4.4 Propagation

For each RMa, UMa, and UMi-street-canyon LOS/NLOS row:

| Vector family | Required points | Expected source | Tolerance |
| --- | --- | --- | --- |
| `RV-PL-<scenario>-LOS` | lower distance, interior first segment, breakpoint−ε, breakpoint, breakpoint+ε, upper distance | Independent worksheet transcribing TR 38.901 V18.1.0 Table 7.4.1-1 | 1e-6 dB |
| `RV-PL-<scenario>-NLOS` | lower, interior, upper; case where candidate NLOS is below LOS | Same plus explicit `max(LOS,NLOS')` check | 1e-6 dB |
| `RV-PL-<scenario>-DOMAIN` | just below/above every distance, height, frequency bound | Model-domain contract | Exact failure |
| `RV-LOS-<scenario>` | lower/interior/upper distance probability | TR 38.901 Table 7.4.2-1 independent worksheet | 1e-12 probability |

The worksheet stores formula text/source coordinates and calculated values, but production code shall not import it.

### 4.5 MCS/CQI and TBS

| Vector family | Required evidence | Tolerance |
| --- | --- | --- |
| RV-CQI-TABLE1 | Every CQI Table 1 row: index, modulation, code rate, efficiency | Exact values |
| RV-MCS-TABLE1 | Every supported MCS Table 1 row | Exact values |
| RV-TBS-SMALL | At least three `N_info ≤ 3824` worked examples | Exact integer bits |
| RV-TBS-LARGE | At least three `N_info > 3824` examples covering both code-rate branches | Exact integer bits |
| RV-TBS-BOUNDARY | Values immediately around quantization and 3824 boundaries | Exact integer bits |

TBS expected values are calculated in a small independent worksheet and cross-checked against a second implementation or published conformance-quality example before production code is accepted.

### 4.6 Schedulers and metrics

| Vector | Inputs | Expected | Tolerance |
| --- | --- | --- | --- |
| RV-RR-001 | 3 backlogged UEs, 1 PRB/slot, 6 slots | stable cyclic order repeated twice | Exact |
| RV-MAXCI-001 | achievable rates 1,3,2 with stable IDs | UE with rate 3 selected | Exact |
| RV-PF-001 | declared instantaneous/average rates | hand-ranked ratio and post-update state | 1e-12 relative |
| RV-FAIR-001 | UE rates `[10,10]` | Jain=1 | Exact within 1e-15 |
| RV-FAIR-002 | UE rates `[10,0]` | Jain=0.5 | Exact within 1e-15 |
| RV-FAIR-003 | UE rates `[1,2,3]` | Jain=6/7 | 1e-15 |
| RV-JITTER-001 | delays 10,14,11 ms | jitter=`(4+3)/2`=3.5 ms | Exact rational ticks |
| RV-COHORT-001 | four deadline-bearing cohort packets: one completed before deadline, one overflow-dropped, one deadline-dropped, one censored | delivery=1/4; deadline-success=1/4; overflow=1/4; deadline-drop=1/4; censor=1/4 | Exact rational |
| RV-UTIL-001 | 80 allocated of 100 PRB-slots, 20 allocated carry zero payload | utilization=0.8; waste=0.25 | 1e-15 |

## 5. Invariants and properties

Property tests use deterministic case seeds recorded on failure.

| Invariant | Requirements |
| --- | --- |
| Time is monotonic; no event is processed twice | TIME-004, TIME-009 |
| Packet identity has exactly one terminal state | QOS-001–QOS-003, QOS-007 |
| Arrived bits = queued + completed + terminally dropped/censored bits, adjusted only by explicitly documented in-service reservation | MAC-009, QOS-002 |
| Cell allocation is integer, nonnegative, and ≤ available PRBs | MAC-002 |
| Queue order remains FIFO under partial service | MAC-009, QOS-001 |
| Path loss and noise outputs are finite inside domain | PROP-004, LINK-002 |
| Increasing Tx gain/power cannot decrease received power | LINK-001 |
| Increasing loss/noise/interference cannot increase SINR | LINK-001–LINK-004 |
| Increasing SINR cannot decrease selected MCS | LINK-010, LINK-011 |
| Same semantic stream path is replayable; adding unrelated paths does not alter it | EXP-002–EXP-004 |
| KPI ratios remain in [0,1] or are typed null | KPI-006, KPI-009, KPI-012 |

## 6. Stochastic verification

Statistical tests verify generators, not a particular random sample:

- Poisson/exponential sample mean and selected quantiles over a fixed large sample with precomputed acceptance bands.
- Bounded uniform samples always satisfy bounds; mean/variance checks use a fixed sample and documented z/tolerance.
- Gaussian shadowing mean and standard deviation checks use deterministic test streams and conservative false-failure thresholds.
- LOS Bernoulli frequency is checked at several fixed probabilities.
- Stream-independence is tested by adding/reordering unrelated entities and comparing target stream digests.

Statistical checks that can fail by chance must state their nominal false-positive rate. Release evidence should include diagnostic values rather than only pass/fail.

## 7. Reproducibility verification

Required cases:

1. same manifest/seed/revision twice in one process;
2. same inputs in separate processes;
3. serial versus parallel execution;
4. original versus permuted input declaration order;
5. scheduler A alone versus scheduler A in a multi-policy experiment;
6. one unrelated UE/bearer added while an existing semantic stream remains identical;
7. clean run bundle reloaded and metrics regenerated.

Semantic digests exclude permitted volatile metadata such as wall-clock start time and absolute artifact path. The exclusion list is schema-versioned and minimal.

## 8. Requirements coverage plan

| Requirement group | Primary verification |
| --- | --- |
| SYS-001–SYS-010 | Integration, dependency, manifest, claims tests |
| CFG-001–CFG-010 | Structural/unit/semantic negative matrix |
| TIME-001–TIME-009 | Event vectors, drift, ordering properties |
| PROP-001–PROP-011 | Geometry, standards vectors, domain/property/statistical tests |
| LINK-001–LINK-014 | Analytical budgets, exact tables, TBS, monotonicity, profile metadata |
| MAC-001–MAC-012 | Policy fixtures, allocation/bit invariants, paired-run tests |
| QOS-001–QOS-010 | Lifecycle, collision, distribution, queue, phase/cohort tests |
| KPI-001–KPI-012 | Hand-ledger and statistical aggregation tests |
| EXP-001–EXP-012 | Schema, identity, seed, serial/parallel, failure injection, bundle tests |
| OPS-001–OPS-010 | CI, clean install, static quality, docs, audit, performance gates |

The repository maintains machine-readable requirements-to-test indexes. An uncovered mandatory requirement blocks release.

## 9. Tolerance policy

- Enumerations, IDs, integer ticks, bits, PRBs, table cells, event orders, hashes: exact.
- dB/log calculations from simple analytical vectors: absolute tolerance ≤1e-9 dB unless external rounded reference limits it.
- 3GPP path-loss formulas: absolute tolerance ≤1e-6 dB against full-precision independent calculation.
- Probabilities and deterministic KPI arithmetic: absolute/relative tolerance ≤1e-12 unless exact rational/integer comparison is possible.
- Statistical distribution checks: test-specific acceptance region and false-positive rate.
- Cross-tool/calibration comparisons: scenario-specific tolerance justified before results are observed.

Production tests may use tighter tolerances; weakening a tolerance after observing failure requires review and rationale.

## 10. Golden and regression data policy

A golden artifact must contain:

- generating requirement/model profile;
- source or reviewed commit;
- reviewer/date;
- semantic fields included/excluded;
- regeneration command;
- reason it is regression rather than independent evidence.

Large stochastic outputs are never committed as undifferentiated goldens. Prefer small semantic ledgers and invariant checks.

## 11. Quality gates

### Configuration gate

- schema/normalization vectors pass;
- unit/log conversion vectors pass;
- CI/static quality is green;
- clean installation and manifest digest are reproducible.

### Model implementation gate

- source/version/domain record complete;
- independent vectors populated and reviewed;
- boundary/failure/property tests pass;
- no unsupported fallback path;
- diagnostics reconstruct the model result.

### Release verification gate

- all mandatory requirements map to passing evidence;
- reproducibility matrix passes;
- failed/flaky/quarantined tests are disclosed and block affected claims;
- validation report distinguishes implementation, verification, calibration, and experimental evidence;
- flagship artifacts regenerate from a clean checkout under the supported environment.

## 12. Specification acceptance evidence

The specification baseline is accepted when:

- the verification plan is versioned and reviewed;
- all Tier A requirements have an acceptance method;
- every standards-derived model maps to pinned clauses/tables and an oracle family;
- architecture decisions define time, ordering, units, RNG, link abstraction, interference, package boundaries, and artifacts;
- schema design exposes all scientific inputs and profile IDs;
- an internal consistency check finds no duplicate requirement/ADR/vector IDs or broken local links.
