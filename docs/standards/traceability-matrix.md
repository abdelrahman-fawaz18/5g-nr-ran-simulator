# Standards Baseline and Traceability Matrix

| Field | Value |
| --- | --- |
| Baseline family | 3GPP Release 18 |
| Baseline status | Frozen release; corrections continue through later minor versions |
| Version snapshot | Verified 2026-08-14 from 3GPP Portal and ETSI Deliver |
| Project claim | 3GPP-informed system-level abstraction, not conformance |

## 1. Baseline policy

Release 18 is selected because 3GPP marks it frozen, while Release 19/20 evolution is unnecessary for the Tier A study. Each source below uses an identified ETSI-published Release 18 revision verified on the snapshot date. Versions are pinned per document rather than forced to an artificial shared minor number or silently tracking later corrections.

Version upgrades require a change-impact review. The reviewer must compare affected clauses/tables, update reference vectors, and record whether generated results remain comparable. A versioned URL is authoritative; this repository does not redistribute standards PDFs.

Primary release references:

- [3GPP Release 18 status](https://portal.3gpp.org/desktopmodules/Release/ReleaseDetails.aspx?releaseId=193)
- [3GPP Release 18 overview](https://www.3gpp.org/specifications-technologies/releases/release-18)

## 2. Pinned source inventory

| Key | Document | Pinned version | Publication | Role | Primary source |
| --- | --- | --- | --- | --- | --- |
| S-38901 | 3GPP TR 38.901, *Study on channel model for frequencies from 0.5 to 100 GHz* | 18.1.0, Rel-18 | 2026-02 | Scenarios, path loss, LOS probability, static shadow-fading parameters | [ETSI PDF](https://www.etsi.org/deliver/etsi_tr/138900_138999/138901/18.01.00_60/tr_138901v180100p.pdf) |
| S-38104 | 3GPP TS 38.104, *NR; Base Station radio transmission and reception* | 18.12.0, Rel-18 | 2026-02 | Frequency ranges and FR1/FR2-1 channel bandwidth/SCS/PRB tables | [ETSI PDF](https://www.etsi.org/deliver/etsi_ts/138100_138199/138104/18.12.00_60/ts_138104v181200p.pdf) |
| S-38211 | 3GPP TS 38.211, *NR; Physical channels and modulation* | 18.9.0, Rel-18 | 2026-04 | Numerology, frame/slot structure, PRB definition | [ETSI PDF](https://www.etsi.org/deliver/etsi_ts/138200_138299/138211/18.09.00_60/ts_138211v180900p.pdf) |
| S-38214 | 3GPP TS 38.214, *NR; Physical layer procedures for data* | 18.9.0, Rel-18 | 2026-04 | MCS/CQI tables, target error probability, TBS procedure | [ETSI PDF](https://www.etsi.org/deliver/etsi_ts/138200_138299/138214/18.09.00_60/ts_138214v180900p.pdf) |
| S-38331 | 3GPP TS 38.331, *NR; Radio Resource Control (RRC); Protocol specification* | 18.8.0, Rel-18 | 2026-02 | Event A3 inequality/vocabulary and time-to-trigger context only | [ETSI PDF](https://www.etsi.org/deliver/etsi_ts/138300_138399/138331/18.08.00_60/ts_138331v180800p.pdf) |
| S-23501 | 3GPP TS 23.501, *System architecture for the 5G System* | 18.12.0, Rel-18 | 2026-01 | QoS/5QI terminology and contextual mappings only | [ETSI PDF](https://www.etsi.org/deliver/etsi_ts/123500_123599/123501/18.12.00_60/ts_123501v181200p.pdf) |

TS 38.306 is not part of Tier A. The simulator does not model UE capability signaling or band combinations, so citing that specification would add apparent scope without an implemented requirement.

## 3. Standards-to-requirements traceability

Status values are `proposed`, `implemented`, `verified`, `limited`, or `context-only`. A row
advances only when the named implementation and independent evidence are recorded.

| Trace ID | Source location | Project interpretation and supported domain | Requirements | Verification method | Status |
| --- | --- | --- | --- | --- | --- |
| STD-FR-001 | S-38104 §5.1, Table 5.1-1 | FR1 is 410–7125 MHz; Tier A lower bound is narrowed to 500 MHz because S-38901 begins at 0.5 GHz. FR2 is excluded. | CFG-007, LINK-007 | Boundary configuration matrix | Verified |
| STD-RB-001 | S-38104 §5.3.2, Table 5.3.2-1 | Enumerate every valid FR1 SCS/channel-bandwidth pair and exact `N_RB`; `N/A` combinations fail. | CFG-007, LINK-007 | Exhaustive independent table fixture | Verified |
| STD-FR2-001 | S-38104 §5.1 Table 5.1-1; §5.3.2 Table 5.3.2-2 | FR2-1 is 24.25–52.6 GHz; enumerate exact 60/120 kHz SCS and 50/100/200/400 MHz `N_RB` combinations. | DYN-FR2-001 | Exhaustive exact table/boundary fixture | Verified |
| STD-NUM-001 | S-38211 §4.2, Table 4.2-1 | Tier A permits μ=0,1,2 (15/30/60 kHz) with normal CP. | TIME-003, LINK-008 | Exact enumeration fixture | Verified |
| STD-TIME-001 | S-38211 §4.3.2, Table 4.3.2-1 | Normal CP has 14 symbols/slot and 1,2,4 slots/ms for μ=0,1,2. | TIME-001, TIME-003, LINK-008 | Exact slot-duration vectors | Verified |
| STD-RB-002 | S-38211 §4.4.4.1 | One PRB contains 12 consecutive subcarriers. | LINK-008, KPI-008 | Exact bandwidth calculation | Verified |
| STD-SCEN-001 | S-38901 §7.2, Tables 7.2-1 and 7.2-3 | UMi-street-canyon, UMa, and RMa scenario vocabulary and evaluation context. Tier A permits custom layouts but labels deviations. | PROP-003, PROP-004, PROP-011 | Scenario-domain configuration review | Verified |
| STD-PL-001 | S-38901 §7.4.1, Table 7.4.1-1 | Implement LOS/NLOS path-loss rows, breakpoint expressions, height/frequency/distance limits, NLOS max rule, and shadow sigma for RMa. | PROP-002–PROP-005, PROP-007, PROP-009 | Independent spreadsheet/calculator points at lower/interior/breakpoint/upper domains | Verified |
| STD-PL-002 | S-38901 §7.4.1, Table 7.4.1-1 | Same obligations for UMa. | PROP-002–PROP-005, PROP-007, PROP-009 | Independent vectors and continuity check | Verified |
| STD-PL-003 | S-38901 §7.4.1, Table 7.4.1-1 | Same obligations for UMi-street-canyon. | PROP-002–PROP-005, PROP-007, PROP-009 | Independent vectors and continuity check | Verified |
| STD-LOS-001 | S-38901 §7.4.2, Table 7.4.2-1 | Seeded LOS state uses scenario-specific distance probability; explicit state bypasses drawing but not model-domain checks. | PROP-006, EXP-002–EXP-004 | Formula points plus fixed uniform draws | Verified |
| STD-SF-001 | S-38901 §7.4.1, Table 7.4.1-1 | Static Tier A shadow fading uses the row’s log-domain sigma; correlation procedures are deferred. | PROP-007, PROP-008 | Seed replay and distribution sanity checks | Verified |
| STD-MCS-001 | S-38214 §5.1.3.1, Table 5.1.3.1-1 | Tier A uses the one-layer downlink MCS Table 1 modulation order, target code rate, and efficiency. SINR thresholds are a project abstraction, not a 3GPP table. | LINK-009–LINK-012 | Exact table fixture plus threshold monotonicity | Verified |
| STD-TBS-001 | S-38214 §5.1.3.2 | Implement TBS determination for the supported one-codeword domain with explicit RE and layer inputs. | LINK-009, LINK-013 | Independent worked integer cases | Verified |
| STD-CQI-001 | S-38214 §5.2.2.1, Table 5.2.2.1-2 | CQI Table 1 metadata and 10% maximum target transport-block error probability. No standard SINR thresholds are inferred. | LINK-010–LINK-012 | Exact table fixture and claims review | Verified |
| STD-QOS-001 | S-23501 §5.7.2.1 | 5QI is contextual metadata describing QoS treatment; it does not automatically instantiate simulator behavior. | QOS-008, QOS-009 | Schema/negative behavior test | Context-only |
| STD-QOS-002 | S-23501 §5.7.4, Table 5.7.4-1 | An experiment may explicitly adopt selected QoS characteristics, but must configure them and disclose omitted core/RAN procedures. | QOS-008, KPI-006 | Configuration/documentation audit | Context-only |
| STD-HO-001 | S-38331 §5.5.4.4 and `EventTriggerConfig` | Reuse Event A3 neighbour-versus-serving inequality vocabulary and time-to-trigger concept only; project omits RRC signalling/filtering and labels the state machine A3-inspired. | DYN-HO-001–DYN-HO-005 | Hand state-machine vectors and claims review | Context-only |

## 4. Project-derived and non-standard models

The following are intentionally not attributed to 3GPP:

| Model | Project definition | Required disclosure |
| --- | --- | --- |
| Hybrid event/slot kernel | ADR-0001 | Scheduling-time abstraction and event order |
| RNG namespace derivation | ADR-0003 | NumPy engine/version and semantic stream path |
| Analytical SINR threshold profile | ADR-0004 | Formula, implementation margin, uncalibrated status |
| Full-buffer reuse-1 interference | ADR-0005 | Deterministic worst-case/load-independent interpretation |
| Traffic source parameters | Traffic/QoS contract and experiment manifest | Source primitive and parameter justification |
| Scheduler definitions | System requirements and later model docs | PF averaging/initialization and deterministic ties |
| KPI formulas | KPI contract | Definition version, window, population, censoring |
| Activity-coupled interference timing/PRB placement | ADR-0013 | One-slot lag, lowest-contiguous PRBs, and reconstruction records |
| Dynamic shadow evolution | Dynamic-radio requirements/ADR-0013 | Configured correlation distance; no cross-link spatial-consistency claim |
| Mobility and availability state | Dynamic-radio requirements/ADR-0013 | Project state machine, not complete RRC/RLF |
| FR2 beam/blockage availability | Dynamic-radio requirements/ADR-0013 | Configured sensitivity abstraction, not calibrated beam management |

## 5. Implementation traceability record

When code is added, each row above gains or links to:

- implementation symbol/path;
- source-data artifact identifier;
- test identifiers and tolerance;
- implementation commit;
- evidence level under the quality policy;
- deviations or limitations.

No row moves to `verified` until its oracle is independent of the implementation under test.

The configuration layer implements the configuration-domain interpretation for `STD-FR-001`, `STD-RB-001`, `STD-NUM-001`, `STD-TIME-001`, and `STD-RB-002` in `src/nr_ran_sim/config/normalize.py`, with exhaustive table/boundary coverage in `tests/unit/test_normalize.py`. Their status is E1 implemented, not E2 verified radio behavior; the NR capacity layer must reuse or supersede this source data under its own capacity/reference gate.

The radio-link layer implements `STD-SCEN-001`, `STD-PL-001` through `STD-PL-003`, `STD-LOS-001`, and
`STD-SF-001` in `src/nr_ran_sim/radio/geometry.py`, `topology.py`, and `propagation.py`.
Independent clarity-first equations and the retained numeric fixture are in
`tests/reference/test_propagation_reference.py` and
`tests/reference/data/tr38901_path_loss_vectors.yaml`; domain, topology, replay, and full-link
integration evidence is indexed in `docs/verification/radio-link-requirements-index.yaml`.

The NR capacity layer completes reference verification for `STD-RB-001`, `STD-NUM-001`, `STD-TIME-001`,
`STD-RB-002`, `STD-MCS-001`, `STD-TBS-001`, and `STD-CQI-001`. Exact source tables, a separate
integer TBS calculator, retained vectors, boundary/property tests, and artifact evidence are
indexed in `docs/verification/nr-capacity-requirements-index.yaml`. The analytical SINR threshold
remains a project model and is not promoted to a 3GPP or calibrated claim.

The dynamic-radio layer verifies `STD-FR2-001` with an exhaustive independently transcribed Table 5.3.2-2 matrix,
inclusive FR2-1 carrier boundaries, and an unsupported-pair negative test. `STD-HO-001` remains
context-only: the implementation borrows Event A3 inequality/time-to-trigger vocabulary but is
explicitly named A3-inspired and omits RRC procedures. Evidence is indexed in
`docs/verification/dynamic-radio-requirements-index.yaml`.

## 6. Review checklist for a standards version change

1. Confirm Release and publication identity from 3GPP/ETSI primary sources.
2. Diff all referenced clauses and tables.
3. Identify changed requirement, schema, model, and test IDs.
4. Regenerate source-data tables through a reviewed process.
5. Rerun reference, boundary, regression, and flagship experiments.
6. Update model-profile versions if numerical behavior changes.
7. State whether results produced under the prior baseline remain comparable.
