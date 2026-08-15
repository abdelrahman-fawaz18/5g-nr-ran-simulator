# Dynamic-Radio Extension Requirements

| Field | Value |
| --- | --- |
| Extension baseline | 1.0 |
| Status | Implemented; local and cross-platform gates passed |
| Parent requirements | `system-requirements.md` EXT-001 through EXT-004 |
| Profiles | `tier-b-fr1-dynamic-v1`; `tier-b-fr2-availability-v1` |

## 1. Scope and claims

The extension adds deterministic large-scale time variation to the verified static simulator. It does
not implement a complete NR RRC procedure, fast fading, beam training, radio-link monitoring,
RLF/re-establishment, HARQ, or a calibrated FR2 channel. The term *availability outage* below is
a project-defined scheduling-availability state, not 3GPP radio-link failure.

The existing `tier-a-fr1-static-v1` profile and its semantic result remain unchanged.

## 2. Activity-coupled interference

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| DYN-INT-001 | `activity-coupled-reuse1-v1` shall use reuse factor one and a one-slot causal lag: scheduling at slot `k` observes neighbour PRB activity committed in slot `k-1`. | Two-cell timing vector; declaration-order replay. |
| DYN-INT-002 | Each allocation shall occupy the lowest numbered contiguous PRBs in this frequency-flat extension. Interference on a served allocation shall include only overlapping active neighbour PRBs. | Exact PRB-mask/overlap vectors. |
| DYN-INT-003 | Signal, noise, and each interferer shall scale by the evaluated PRB bandwidth and be summed in linear watts. | Hand-calculated one/two-interferer vectors. |
| DYN-INT-004 | Slot zero shall use an explicit configured initial neighbour-load fraction. Idle neighbours shall contribute no data-PRB interference after the causal lag. | Zero/full/partial-load fixtures. |
| DYN-INT-005 | The artifact shall retain prior activity masks, overlap counts, per-cell powers, and the resulting SINR used for every dynamic scheduling interval. | Result-schema and reconstruction test. |

This model represents aligned co-channel downlink data PRBs. It excludes TDD cross-link
interference, control/reference-signal interference, frequency-selective fading, and power control.

## 3. Channel cadence and shadow evolution

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| DYN-CH-001 | Geometry/path loss shall update at a configured positive interval aligned to complete slots; activity-coupled SINR shall update every slot. | Configuration matrix and event-order trace. |
| DYN-CH-002 | `correlated_dynamic` shadowing shall use one independent per-link Gauss-Markov stream with `rho = exp(-delta_distance/correlation_distance)` and `X_k = rho X_(k-1) + sqrt(1-rho^2) sigma Z_k`. | Zero-distance, hand-vector, variance, and replay tests. |
| DYN-CH-003 | Correlation distance shall be an explicit positive scenario input. Correlation is along each UE trajectory only; cross-link and map-consistent spatial correlation are not claimed. | Schema and profile metadata tests. |
| DYN-CH-004 | LOS/NLOS state shall remain the run-static explicit/probability state unless a future profile defines state transitions. | Regression and metadata assertion. |

## 4. Mobility and handover abstraction

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| DYN-MOB-001 | `linear-reflect-v1` shall move each configured UE at explicit Cartesian velocity and reflect exactly at explicit rectangular bounds without overshoot or changing height. | Analytical position/boundary vectors. |
| DYN-MOB-002 | UE position updates shall occur in topology/control phase before link/association evaluation at the same tick. | Semantic event-order test. |
| DYN-HO-001 | Measurements shall use unfiltered long-term reference-signal received power from the dynamic large-scale link state. | Known link-ranking fixture. |
| DYN-HO-002 | The A3-inspired entry condition shall be `M_neighbour - M_serving > offset + hysteresis`; the leave/cancel condition shall be `< offset - hysteresis`. The candidate shall remain continuously entered for the configured time-to-trigger before handover. | Entry/leave/equality/TTT vectors. |
| DYN-HO-003 | Exact metric ties shall select lexical cell ID. Handover shall switch association at the decision tick and make the UE unavailable for the configured interruption interval. | Tie and interruption fixtures. |
| DYN-HO-004 | Returning to the immediately previous serving cell within the configured ping-pong window shall be counted once as a ping-pong handover. | Three-cell state-machine fixture. |
| DYN-HO-005 | Handover decisions, pending-candidate state, interruption intervals, and ping-pong classification shall be serialized. | Artifact/replay test. |

The condition borrows TS 38.331 Event A3 vocabulary and inequality structure but omits RRC
signalling, measurement filtering, offsets other than the configured A3 offset, failures, and
conditional handover. It is therefore labeled `a3-inspired-long-term-rsrp-v1`.

## 5. Availability outage and recovery

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| DYN-AVL-001 | Availability shall enter outage when serving-link SINR remains at or below the configured entry threshold for the configured entry duration. | Threshold/duration vectors. |
| DYN-AVL-002 | Availability shall recover only when serving-link SINR remains at or above the configured exit threshold for the configured recovery duration; exit threshold shall exceed entry threshold. | Hysteresis/recovery vectors. |
| DYN-AVL-003 | An interrupted or outage UE shall be excluded from scheduling eligibility while traffic and deadlines continue. | Queue/service integration fixture. |
| DYN-AVL-004 | Sampled outage fraction, outage/recovery transitions, and handover interruption time shall be machine-readable. | KPI hand vector. |

## 6. FR2-1 availability profile

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| DYN-FR2-001 | FR2-1 shall accept only 24.25–52.6 GHz and exact 60/120 kHz SCS/channel-bandwidth/PRB combinations from TS 38.104 V18.12.0 Table 5.3.2-2. | Exhaustive exact table/boundary tests. |
| DYN-FR2-002 | The first FR2 profile shall be limited to UMa and UMi-street-canyon TR 38.901 large-scale path loss within the existing equation domains. RMa FR2 shall fail closed. | Positive/negative domain matrix. |
| DYN-FR2-003 | Each cell shall declare a finite horizontal beam codebook. Gain shall be the maximum over `max(sidelobe_gain, peak_gain - 12*(wrapped_delta/beamwidth)^2)`; exact ties use lexical beam ID. | Angular/tie/reference vectors. |
| DYN-FR2-004 | Blockage shall be explicit link/time intervals with configured nonnegative excess loss. Overlaps shall use the largest active loss, and boundaries shall be `[start,end)`. | Interval/boundary vectors. |
| DYN-FR2-005 | Dynamic link records shall expose selected beam, beam gain, blockage state/loss, base path loss, shadow, received power, interference, and availability. | Reconstruction/schema test. |

This profile is a controlled sensitivity model. Its configured beams are not an antenna-array or
beam-management implementation, and its explicit blockage schedule is not a stochastic human or
building blockage calibration.

## 7. Dynamic KPI extension

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| DYN-KPI-001 | KPI definition `dynamic-radio-1.0` shall report handover count, ping-pong count/ratio, interruption fraction, sampled availability-outage fraction, and association changes per UE and system where meaningful. | Hand-constructed state ledger. |
| DYN-KPI-002 | Every ratio shall use explicit observation/time denominators and preserve zero versus undefined values. | Zero-denominator/null test. |

## 8. Reproducibility and regression

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| DYN-REP-001 | Mobility, dynamic shadow, blockage, handover, and interference state shall replay for fixed configuration/seed/revision. | Same/fresh-process digest tests. |
| DYN-REP-002 | Scheduler-changing comparisons shall preserve mobility, channel, and blockage inputs through the existing exogenous identity. | Paired-policy state fingerprint test. |
| DYN-REP-003 | All approved static the static radio, capacity, and scheduler layers fixture identities and results shall remain unchanged. | Static digest regression tests. |
