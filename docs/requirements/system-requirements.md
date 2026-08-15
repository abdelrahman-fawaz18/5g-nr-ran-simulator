# System Requirements

| Field | Value |
| --- | --- |
| Baseline | the system specification baseline / version 1.0 |
| Status | Approved specification baseline |
| Scope | Tier A downlink system-level simulator, with explicit Tier B extension points |
| Standards release | 3GPP Release 18; exact document versions are pinned in `../standards/traceability-matrix.md` |
| Verification authority | `../verification/verification-plan.md` |

## 1. Purpose and requirement language

This document converts the project vision into testable engineering requirements. “Shall” is mandatory for the stated tier, “should” is a recommendation, and “may” is optional. A requirement is not satisfied by documentation alone: the verification method in the final column must produce objective evidence.

Requirement identifiers are permanent. A removed requirement is marked deprecated rather than renumbered. Changes to a requirement after this baseline require a decision record and traceability update.

## 2. Tier A supported domain

| Dimension | Tier A contract |
| --- | --- |
| Link direction | Downlink only |
| Frequency range | FR1, with carrier frequency in the overlap of the selected propagation model and FR1: 0.5 GHz through 7.125 GHz |
| Scenarios | 3GPP-informed RMa, UMa, and UMi-street-canyon outdoor links |
| Mobility | Static UEs; mobility is a Tier B extension |
| Channel | Large-scale path loss, LOS/NLOS state, optional static shadow fading; no fast-fading waveform model |
| Antennas | Scalar gain per cell/UE; no array pattern, beam sweep, or MIMO precoding |
| Layers | One downlink transmission layer and one codeword |
| Numerology | Normal cyclic prefix; 15, 30, or 60 kHz SCS where the selected FR1 bandwidth/SCS pair is valid in TS 38.104 Table 5.3.2-1 |
| Bandwidth | Any FR1 channel bandwidth/SCS pair explicitly present in the pinned Table 5.3.2-1; invalid pairs are rejected |
| Interference | Noise-limited and deterministic full-buffer reuse-1 modes; activity-coupled interference is Tier B |
| Link adaptation | CQI/MCS Table 1 family, 10% target transport-block error probability, analytical threshold profile with an explicit implementation margin |
| PHY errors | Capacity abstraction; no HARQ timing/combining and no claim of calibrated BLER prediction |
| Scheduling | Round Robin, Max-C/I, and Proportional Fair |
| Traffic | Periodic, Poisson, and bounded-uniform inter-arrival sources; constant or bounded-uniform packet sizes |
| Experiment mode | Seeded independent replications and paired scheduler comparisons |

The model-specific height and distance domains remain those in the pinned 3GPP path-loss table. The configuration validator must enforce the applicable scenario row, not only the broad values above.

## 3. System and domain requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| SYS-001 | The simulator shall model a configuration-driven downlink RAN at cell, UE, bearer, packet, scheduling-interval, and PRB-allocation granularity. | End-to-end scenario test exposes each named entity and transition. |
| SYS-002 | The simulator shall identify its fidelity tier, model profile versions, configuration schema version, and result schema version in every run manifest. | Manifest schema and serialization test. |
| SYS-003 | A fixed normalized configuration, master seed, replication identifier, code revision, and supported environment shall produce an identical semantic event trace and metric dataset. | Repeated-run digest test. |
| SYS-004 | Invalid or unsupported scientific input shall fail before simulation begins; the system shall not silently clip, coerce, or substitute a model. | Negative configuration matrix. |
| SYS-005 | Validated scenario inputs shall be immutable during a run; state changes shall occur only through typed simulation events. | Type/static checks and mutation tests. |
| SYS-006 | Runtime implementation code shall not import or execute files outside the installable package. | Import-boundary check. |
| SYS-007 | Every entity and event shall have a stable, run-local identifier suitable for trace correlation. | Identifier uniqueness/integrity test. |
| SYS-008 | Every warning, fallback, model-domain violation, dropped packet, and failed replication shall be represented as structured data. | Event/result schema tests. |
| SYS-009 | Core domain, radio-model, policy, orchestration, and reporting components shall be independently testable and shall follow the dependency rules in the architecture overview. | Architecture/import contract test. |
| SYS-010 | The simulator shall state that it is 3GPP-informed and shall not emit compliance, calibration, real-time, or commercial-planning claims. | Documentation/metadata assertion test. |

## 4. Configuration and units requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| CFG-001 | Scenario and experiment documents shall include an explicit semantic schema version. | Schema validation tests. |
| CFG-002 | Unknown fields shall be rejected by default; extension fields shall be confined to a documented namespace. | Unknown-field negative tests. |
| CFG-003 | Physical quantities at the human-authored boundary shall contain both a numeric value and an allowed unit. | Unit-object schema tests. |
| CFG-004 | Boundary quantities shall be converted once into canonical SI-domain representations; inner-loop code shall not parse unit strings. | Normalization tests and dependency inspection. |
| CFG-005 | Logarithmic radio quantities shall retain explicit `dB`, `dBm`, or `dBi` types and shall not be added to linear power values without conversion. | Dimensional/type tests. |
| CFG-006 | Validation errors shall identify the field path, received value, expected type/domain, and governing requirement or standard reference when applicable. | Error snapshot tests. |
| CFG-007 | Cross-field validation shall reject invalid FR/SCS/bandwidth combinations, incompatible model/scenario selections, nonpositive durations, and impossible phase windows. | Semantic validation matrix. |
| CFG-008 | Normalization shall expand all defaults into a canonical manifest and compute a SHA-256 configuration digest. | Canonicalization and hash tests. |
| CFG-009 | Defaults that affect scientific meaning shall be documented, versioned, and present in the normalized manifest. | Schema/default inventory review. |
| CFG-010 | Secret values and machine-specific absolute paths shall not be valid scenario fields. | Schema and security tests. |

## 5. Time and event requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| TIME-001 | Simulation time shall use integer nanosecond ticks; binary floating-point values shall not be event-queue keys. | Unit and long-run drift tests. |
| TIME-002 | The kernel shall be hybrid: arbitrary-time exogenous events with radio scheduling and service on slot boundaries. | Timeline integration test. |
| TIME-003 | Normal-CP slot duration shall be derived from the configured numerology; Tier A scheduling shall occur once per slot. | TS 38.211 reference vectors. |
| TIME-004 | Equal-time events shall be ordered by `(tick, phase, entity key, local sequence)` and shall never depend on container iteration order. | Permuted-input determinism test. |
| TIME-005 | The mandatory same-time phase order shall be prior-slot completion, deadline expiration, topology/control update, packet arrival, link/association update, scheduling, service reservation, then observation emission. | Golden semantic event test. |
| TIME-006 | A transport block completing exactly at a packet deadline shall complete before expiration and shall count as on time. | Boundary deadline test. |
| TIME-007 | A packet arriving exactly at a slot boundary shall be visible to that boundary’s scheduler; an arrival between boundaries shall wait until the next boundary. | Arrival eligibility tests. |
| TIME-008 | Simulation phases shall be warm-up, measurement, and drain; traffic generation shall stop at measurement end and pending measurement-cohort packets may resolve during drain. | Phase-transition test. |
| TIME-009 | The kernel shall reject events scheduled earlier than current time and detect non-monotonic processing. | Invariant/failure tests. |

## 6. Geometry and propagation requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| PROP-001 | Coordinates shall be three-dimensional Cartesian positions in metres in a declared local coordinate system. | Geometry unit tests. |
| PROP-002 | The system shall compute and expose both horizontal 2D and direct 3D link distance. | Analytical geometry vectors. |
| PROP-003 | Tier A shall implement RMa, UMa, and UMi-street-canyon LOS and NLOS path-loss models from TR 38.901 V18.1.0 Table 7.4.1-1. | Independent table/equation vectors. |
| PROP-004 | Path-loss evaluation shall enforce each equation’s carrier-frequency, height, and distance applicability domain. | Boundary and out-of-domain matrix. |
| PROP-005 | For a scenario where the standard defines NLOS path loss as the maximum of LOS and a candidate NLOS expression, the implementation shall apply that maximum exactly. | Piecewise reference vectors. |
| PROP-006 | LOS/NLOS state shall support explicit input and a seeded probability mode based on TR 38.901 Table 7.4.2-1. | Probability formula and seeded-state tests. |
| PROP-007 | Tier A shadow fading, when enabled, shall be a static per-link zero-mean Gaussian value in dB with scenario/state sigma from the pinned model table. | Distribution and deterministic replay tests. |
| PROP-008 | Tier A shall not claim spatially correlated shadow fading, fast fading, blockage, oxygen absorption, or penetration loss unless the corresponding extension profile is selected and verified. | Model-profile metadata test. |
| PROP-009 | Every path-loss result shall include scenario, propagation state, model identifier/version, distances, carrier frequency, path loss, shadow term, and domain status. | Diagnostic record schema test. |
| PROP-010 | Cell association shall use long-term received reference power excluding instantaneous fast fading and traffic load; exact ties shall select the lexically smallest stable cell identifier. | Association fixtures. |
| PROP-011 | Random topology generation shall be bounded by the configured area and minimum-distance rules and shall fail if requested density is infeasible within a configured attempt budget. | Feasible/infeasible topology tests. |

## 7. Link budget and radio-resource requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| LINK-001 | Received power shall expose transmit power or PSD, antenna gains, path loss, shadow/penetration loss, implementation loss, and the resulting power in both linear and logarithmic forms. | Hand-calculated link-budget vector. |
| LINK-002 | Thermal noise shall use a versioned constant of −174 dBm/Hz, configured noise-equivalent bandwidth, and receiver noise figure. | Analytical noise vectors. |
| LINK-003 | Interference powers shall be summed in linear units before conversion to dB. | Two-interferer analytical vector. |
| LINK-004 | SINR shall be computed as signal power divided by the sum of interference and noise in linear units, with each component exportable. | Analytical SINR vector. |
| LINK-005 | Tier A shall support `noise_limited` and `full_buffer_reuse1` interference profiles; their identifiers shall appear in run metadata. | Profile integration tests. |
| LINK-006 | `full_buffer_reuse1` shall treat each configured co-channel non-serving cell as transmitting over all PRBs at its configured or deterministically derived PSD; a configured total cell power shall be spread uniformly over the active transmission bandwidth, and the profile shall not depend on neighbour scheduler activity. | Deterministic power-normalization and interference fixture. |
| LINK-007 | Valid FR1 SCS/bandwidth pairs and PRB counts shall match TS 38.104 V18.12.0 Table 5.3.2-1 exactly. | Exhaustive table test. |
| LINK-008 | One PRB shall represent 12 consecutive subcarriers and normal CP shall use 14 OFDM symbols per slot. | TS 38.211 reference tests. |
| LINK-009 | Tier A shall use one downlink layer and one codeword and shall expose configured non-data RE overhead. | Capacity input/output test. |
| LINK-010 | Tier A shall derive an analytical achievable-efficiency cap from SINR and required implementation margin, select the highest CQI Table 1 efficiency not exceeding that cap, then select the highest MCS Table 1 efficiency not exceeding the selected CQI efficiency; the profile shall be labeled uncalibrated. | Threshold/table and metadata tests. |
| LINK-011 | The CQI threshold rule shall choose the highest supported CQI whose threshold does not exceed observed SINR; below the lowest threshold it shall return outage rather than a default efficiency. | Boundary/monotonicity tests. |
| LINK-012 | The target transport-block error probability for CQI Table 1 shall be 0.1; Tier A shall not present this target as a calibrated SINR-to-BLER curve. | Configuration and claims review. |
| LINK-013 | Transport-block size shall follow TS 38.214 V18.9.0 Clause 5.1.3.2 for the supported one-layer domain, using explicit data-RE inputs. | Independent integer TBS vectors. |
| LINK-014 | Tier A PHY service shall be a capacity abstraction without HARQ timing, combining, or waveform errors; packet losses shall be attributed only to modeled causes and labeled accordingly. | Event-cause and metric tests. |

## 8. MAC and scheduling requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| MAC-001 | A scheduler shall receive a read-only observation and return an explicit allocation decision without mutating global state. | Interface and mutation tests. |
| MAC-002 | Every allocation shall use nonnegative integer PRBs, remain within cell capacity, and reference only eligible attached UEs with nonempty queues. | Property/invariant tests. |
| MAC-003 | The resource allocator shall define deterministic treatment of PRB remainders and exact metric ties. | Tie/remainder fixtures. |
| MAC-004 | Round Robin shall maintain a deterministic rotating cursor per cell and shall not rank by channel quality. | Known-sequence fixture. |
| MAC-005 | Max-C/I shall rank eligible UEs by the documented instantaneous achievable payload metric and break ties by stable UE identifier. | Known-ranking fixture. |
| MAC-006 | Proportional Fair shall rank by instantaneous achievable rate divided by exponentially averaged served rate, with a configured averaging coefficient and explicit initialization floor. | Hand-calculated multi-slot fixture. |
| MAC-007 | Scheduler-specific state shall be serializable in semantic traces and isolated between replications. | Replay/state isolation tests. |
| MAC-008 | Scheduler comparison runs shall receive identical exogenous topology, propagation, and traffic streams. | Paired-seed manifest test. |
| MAC-009 | Partial packet service shall preserve FIFO order and exact remaining-bit accounting. | Queue service fixture. |
| MAC-010 | Unused allocation, allocation made to an empty queue, and allocation that cannot carry payload shall be separately observable. | Waste-accounting tests. |
| MAC-011 | Tier A shall not model uplink grants, control-channel contention, HARQ processes, or RLC/PDCP behavior. | Model profile assertion. |
| MAC-012 | A QoS-aware scheduler may be added only as Tier B and shall not alter baseline policy definitions. | Interface/regression review. |

## 9. Traffic, queue, and QoS requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| QOS-001 | Each UE bearer shall own a FIFO queue of individually identified packets. | Queue identity/order tests. |
| QOS-002 | Packets shall preserve arrival tick, payload bits, optional deadline tick, first-service tick, completion tick, and terminal cause. | Lifecycle schema/invariant tests. |
| QOS-003 | Multiple packets may share the same arrival tick without overwrite or implicit aggregation. | Collision fixture. |
| QOS-004 | Tier A shall support periodic, Poisson, and bounded-uniform inter-arrival sources plus constant and bounded-uniform packet sizes. | Deterministic and distribution tests. |
| QOS-005 | Traffic-source RNG shall be independent per bearer and independent from radio/channel streams. | Stream perturbation test. |
| QOS-006 | Queue capacity shall be explicitly configured in packets and/or bits, with deterministic tail drop when a limit is exceeded. | Overflow boundary tests. |
| QOS-007 | Deadline expiration, queue overflow, simulation censoring, and modeled PHY failure shall be distinct terminal causes. | Cause enumeration tests. |
| QOS-008 | Optional 5QI metadata shall be descriptive only; the simulator shall not infer unconfigured core-network, RLC, admission-control, or end-to-end behavior from a 5QI value. | Schema and negative behavior test. |
| QOS-009 | Application profiles shall be user-defined compositions of source, packet-size, queue, and deadline parameters rather than hard-coded names. | Configuration substitution test. |
| QOS-010 | Traffic generated during warm-up shall affect state but shall not enter the measurement cohort; no new packets shall be generated during drain. | Phase/cohort test. |

## 10. KPI requirements

The normative formulas, windows, populations, and censoring treatment are in `kpi-contract.md`.

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| KPI-001 | All KPI records shall include name, definition version, unit, aggregation level, population filter, interval, sample count, and run identifier. | Result schema test. |
| KPI-002 | The simulator shall report offered load, scheduled capacity, served throughput, and completed-payload goodput as distinct quantities. | Hand-constructed event ledger. |
| KPI-003 | Queueing delay, service span, and packet system delay shall be reported separately. | Packet lifecycle vector. |
| KPI-004 | Delay percentiles shall identify the percentile method, completed-packet population, sample count, and censor count. | Statistical fixture. |
| KPI-005 | Jitter shall use the contract’s mean absolute successive packet-delay variation per bearer and shall be undefined for fewer than two completions. | Analytical sequence test. |
| KPI-006 | Delivery, deadline-success, overflow-drop, and censor ratios shall use explicit denominators and terminal causes. | Cohort ledger test. |
| KPI-007 | Jain fairness shall be computed over active UEs with positive offered load, and the active population shall be exported. | Analytical fairness vectors. |
| KPI-008 | Spectral efficiency shall use the actual transmission bandwidth `N_RB × 12 × SCS`, not nominal channel bandwidth. | Analytical vector. |
| KPI-009 | PRB utilization and wasted-allocation ratio shall use PRB-slot counts and shall remain within [0,1]. | Resource ledger test. |
| KPI-010 | Aggregates shall be available per bearer, UE, application class, cell, replication, and system where meaningful. | Schema/grouping integration test. |
| KPI-011 | Stochastic comparisons shall retain per-replication values and report paired differences and confidence intervals. | Multi-seed analysis fixture. |
| KPI-012 | Missing, undefined, censored, and zero-valued metrics shall remain distinguishable in machine-readable output. | Serialization test. |

## 11. Experiment and reproducibility requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| EXP-001 | An experiment manifest shall identify base scenario, sweep factors, scheduler set, master seed, replication IDs, warm-up, measurement, drain, and output schema. | Manifest schema test. |
| EXP-002 | The master seed shall be a 128-bit hexadecimal string; semantic RNG streams shall be derived without order-dependent spawning. | Seed derivation vectors. |
| EXP-003 | RNG engine, engine version, namespace path, and derived seed material shall be recorded. | Run metadata test. |
| EXP-004 | Exogenous streams shall be paired across scheduler policies; policy-internal randomness shall use a separate namespace. | Perturbation and paired-run tests. |
| EXP-005 | A parameter sweep shall reject duplicate normalized run identities. | Sweep collision test. |
| EXP-006 | Run identity shall be a digest of normalized scenario, experiment factor values, replication ID, model profiles, and code revision. | Hash/reference test. |
| EXP-007 | Parallel execution shall not change any run’s semantic output or RNG stream. | Serial/parallel equivalence test. |
| EXP-008 | A failed replication shall be retained with cause and shall not be silently omitted from aggregation. | Failure injection test. |
| EXP-009 | Confidence-interval method and confidence level shall be versioned; paired policy comparisons shall operate on paired replication differences. | Statistical reference test. |
| EXP-010 | Plots and summary tables shall be generated only from saved, schema-valid metric data. | Reporting provenance test. |
| EXP-011 | Every run bundle shall record Git revision, dirty state, Python/dependency versions, platform, normalized manifests, and content hashes. | Bundle inventory test. |
| EXP-012 | A smoke profile and a showcase profile shall be separate manifests with recorded runtime/memory budgets. | Profile existence/performance gate. |

## 12. Operational and quality requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| OPS-001 | The project shall be installable from a clean checkout on the supported Python versions declared in the configuration foundation. | Clean-environment CI job. |
| OPS-002 | Core package code shall pass formatting, linting, and strict static typing with reviewed, local exceptions only. | CI quality jobs. |
| OPS-003 | Automated tests shall include unit, reference-vector, invariant/property, integration, reproducibility, statistical, regression, and performance layers. | Test inventory report. |
| OPS-004 | Every standard-derived model shall have at least one independent oracle and lower/interior/breakpoint/upper-domain cases where applicable. | Requirements-to-test traceability. |
| OPS-005 | Test and result tolerances shall be justified by quantity type; exact integer tables shall not use approximate comparison. | Verification-plan review. |
| OPS-006 | Structured logs shall include run/event identifiers but shall not be the authoritative metric store. | Logging/result separation test. |
| OPS-007 | Generated artifacts shall be written outside source directories and shall never overwrite an existing run identity without an explicit force operation. | Filesystem integration test. |
| OPS-008 | Repository documentation shall contain no broken internal links and shall link every implemented model to requirements, source, and verification evidence. | Documentation link/traceability check. |
| OPS-009 | Dependencies and reference datasets shall have pinned versions, provenance, and license compatibility recorded before public release. | Release audit. |
| OPS-010 | The public-ready release shall expose limitations as prominently as results and shall not promote E0/E1 work as E2–E4 evidence. | Claims audit. |

## 13. Deferred Tier B requirements

The following are named boundaries, not the system specification baseline commitments to implement them:

| ID | Deferred requirement |
| --- | --- |
| EXT-001 | Activity-coupled per-PRB inter-cell interference driven by neighbour allocations. |
| EXT-002 | Time/spatially correlated shadowing, fast-fading or effective-SINR compression, and calibrated BLER curves. |
| EXT-003 | Mobility, measurements, handover hysteresis/time-to-trigger, interruption, outage, and ping-pong metrics. |
| EXT-004 | FR2-1 with explicit antenna-array gain, beam selection, and blockage assumptions. |
| EXT-005 | QoS/deadline-aware scheduling after baseline scheduler verification. |

## 14. Baseline change control

A requirement change must state which verification artifacts, ADRs, schema fields, and standards mappings are affected. A change that weakens fidelity or verification also requires an update to the claims boundary.
