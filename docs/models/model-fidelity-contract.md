# Model Fidelity Contract

| Field | Tier A baseline |
| --- | --- |
| Profile identifier | `tier-a-fr1-static-v1` |
| Evidence state | Radio and capacity procedures are E2 reference-verified; scheduler, KPI, and experiment behavior is E1 implementation-verified; flagship conclusions are E4 experimentally supported; no profile is E3 calibrated |
| Standards family | Pinned Release 18 sources in the traceability matrix |
| Intended use | Controlled scheduler/QoS comparisons in static FR1 scenarios |
| Prohibited use | Coverage planning, conformance, real-network prediction, safety/mission assurance |

The dynamic-radio layer provides two opt-in E1 extension profiles: `tier-b-fr1-dynamic-v1` and
`tier-b-fr2-availability-v1`. Their exact additions and exclusions are defined in the
[dynamic-radio guide](../radio/mobility-handover-and-fr2.md). They do not alter Tier A.

## 1. Fidelity principle

The simulator represents only the mechanisms necessary to study a scoped system-level question. Every omitted mechanism is a boundary, not an implicit ideal implementation. A run’s model-profile identifier and component subprofiles must make those boundaries machine visible.

## 2. Tier A model stack

| Layer | Represented | Not represented |
| --- | --- | --- |
| Scenario | Static RMa, UMa, UMi-street-canyon geometry; explicit or generated sites/UEs | Indoor topology, factory, highway, terrain/building maps |
| Antenna | Scalar transmit/receive gains and configured losses | Element patterns, sector patterns unless explicitly supplied, arrays, beams, polarization |
| Propagation | 3D distance, LOS/NLOS path loss, optional static log-normal shadowing | Fast fading, Doppler, blockage, O2I penetration, spatial consistency |
| Association | Long-term received-power maximum with deterministic ties | Load balancing, measurement filtering, cell reselection/handover |
| Link budget | Tx power/PSD, gains/losses, thermal noise, noise figure, interference, SINR | RF impairments, adjacent-channel interference, power control loops |
| Interference | Noise-limited or full-buffer cochannel reuse-1 | Activity coupling, TDD cross-link interference, beam-aware interference |
| Resource grid | FR1 PRB count, 12 subcarriers/PRB, slot/numerology, configurable data RE overhead | Exact control/reference-signal mapping, mini-slots, mixed numerologies |
| Link adaptation | One layer; Table 1 MCS/CQI family; analytical SINR thresholds; TBS procedure | Calibrated EESM/MIESM, per-RB fading compression, CSI delay/error |
| PHY reliability | Capacity abstraction bounded by a 10% target-error design point | Waveform decoding, code-block curves, HARQ processes/combining |
| MAC | PRB allocation, FIFO service, RR/Max-CI/PF policies | PDCCH, BSR/SR, RLC/PDCP, uplink scheduling |
| Traffic/QoS | Packet sources, queues, deadlines, drops, application classes | TCP/IP dynamics, 5GC, admission control, end-to-end transport delay |
| Statistics | Seeded replications, paired comparisons, confidence intervals | Claims beyond the configured model population |

## 3. Propagation fidelity

### 3.1 Domain enforcement

The selected TR 38.901 row governs valid `f_c`, `d_2D`, `d_3D`, `h_BS`, `h_UT`, and any breakpoint terms. The evaluator returns a domain error before evaluating logarithms or extrapolating. The global Tier A carrier range is 0.5–7.125 GHz, but a narrower row-specific limit wins—for example the RMa evaluation context is limited to frequencies supported by its pinned row/context.

### 3.2 LOS and shadowing

- `explicit`: LOS/NLOS is supplied per link and retained in the manifest.
- `probability_static`: one seeded draw per link uses the selected scenario probability and remains fixed for the run.
- `shadowing=off`: zero dB shadow term, explicitly recorded.
- `shadowing=independent_static`: one seeded Gaussian draw per link using the scenario/state sigma.

No Tier A mode introduces temporal or spatial correlation.

The radio-link implementation and evidence are documented in
[`../radio/radio-propagation-and-link-budget.md`](../radio/radio-propagation-and-link-budget.md) and the radio-link
requirements index. E2 here means equation/reference verification under the stated inputs; it
does not mean measurement calibration.

## 4. Link budget fidelity

For an allocated spectral region, all power-domain calculations use linear watts internally:

`P_rx_dBm = P_tx_dBm + G_tx_dBi + G_rx_dBi - L_path_dB - L_shadow_dB - L_penetration_dB - L_misc_dB`.

`N_dBm = -174 dBm/Hz + 10 log10(B_noise_Hz) + NF_dB`.

`SINR_linear = S_watt / (N_watt + sum(I_watt))`.

Every term is exportable. Antenna gains are scalar Tier A inputs; using them does not imply beamforming. Penetration defaults to zero because the Tier A outdoor-link profile does not implement O2I.

For association, the uniform transmit PSD is converted to received power over one subcarrier
bandwidth. This long-term reference-RE power is the Tier A RSRP proxy; exact ties use the stable
lexical cell identifier. The snapshot retains all candidate links, not only the serving link.

## 5. Interference fidelity

- `noise_limited-v1`: `I=0`; useful for unit checks and isolated scheduler mechanics.
- `full_buffer_reuse1-v1`: every configured non-serving cochannel cell transmits across every PRB at configured power spectral density. When authoring supplies total cell transmit power, normalization spreads that power uniformly over the active transmission bandwidth and exports the derived PSD. This is a deterministic upper-load abstraction and does not respond to neighbour traffic or scheduling.

The profile must be visible in every metric record. Results from the two profiles are not pooled. Activity-coupled interference requires a new Tier B profile and regression comparison.

### 5.1 Tier B dynamic extension

`activity-coupled-reuse1-v1` uses the previous slot's scheduled PRB count with reuse one and
lowest-contiguous-PRB overlap. It is causal and load-responsive, but remains frequency-flat and
omits control/reference-signal, cross-link, and adjacent-channel interference. Dynamic shadowing
uses independent per-link distance-domain Gauss-Markov evolution; it is not map-consistent spatial
correlation. Handover and scheduling availability are project state machines, not complete RRC or
radio-link-failure procedures.

The FR2-1 profile adds configured horizontal parabolic beams and explicit excess-loss blockage
windows. These are sensitivity inputs rather than antenna-array, beam-training, or calibrated
blockage models. Its evidence level is E1 implemented and reference-bounded, not E3 calibrated.

## 6. Link-adaptation fidelity

3GPP specifies CQI/MCS parameters and target error behavior but does not provide a universal SINR-to-CQI threshold table. Tier A therefore defines an openly project-derived threshold profile:

`gamma_threshold_linear(i) = ((2 ^ eta_i) - 1) × 10 ^ (implementation_margin_dB / 10)`

`gamma_threshold_dB(i) = 10 log10((2 ^ eta_i) - 1) + implementation_margin_dB`

where `eta_i` is the pinned CQI Table 1 spectral efficiency and `implementation_margin_dB` is a required manifest value with no hidden default. The highest CQI whose threshold is met is selected; otherwise the link is in outage. The service model then selects the highest MCS Table 1 efficiency that does not exceed the chosen CQI efficiency and uses that MCS in TBS determination.

This is an analytical AWGN-capacity-gap abstraction. It is monotonic and reproducible, but it is not a calibrated BLER curve. The 0.1 target transport-block error probability documents the CQI Table 1 design point; Tier A does not simulate HARQ or claim per-transmission error prediction. The flagship report must run implementation-margin sensitivity analysis.

The NR capacity implementation, integer procedures, table evidence, and the independent full-allocation
inspection boundary are documented in
[`../radio/nr-resource-grid-and-link-adaptation.md`](../radio/nr-resource-grid-and-link-adaptation.md).

A future `calibrated-eesm` profile must use a separately versioned and license-reviewed dataset, state its waveform/channel assumptions, and cannot silently replace this profile.

## 7. Resource and service fidelity

- Valid PRB counts come from the pinned FR1 table.
- One PRB spans 12 subcarriers.
- Normal CP has 14 symbols/slot.
- The scenario explicitly declares data-symbol/RE overhead.
- One layer and one codeword are used.
- TBS follows the supported portion of the pinned TS 38.214 procedure.
- A transport block supplies queue service capacity; individual PHY code blocks, retransmission timing, and control signaling are absent.

## 8. Queue and latency fidelity

Packets are application-payload units. System delay is simulated RAN queue/service delay only. It excludes source encoding, transport stack, core, propagation outside the modeled link, and receiver application processing. Documentation must not label it end-to-end application latency without that qualifier.

## 9. Scheduler comparison validity

A comparison is valid within this profile only when:

- scheduler policy is the intended changed factor;
- normalized scenario and model profiles are identical;
- exogenous RNG streams are paired;
- warm-up/measurement/drain rules are identical;
- per-replication values and paired confidence intervals are retained;
- interference-profile and implementation-margin sensitivity are reported when they materially affect ordering.

## 10. Known bias directions

| Simplification | Likely effect or uncertainty |
| --- | --- |
| No fast fading | Removes short-term channel diversity and may understate opportunistic-scheduling effects. |
| Full-buffer interferers | Can understate SINR compared with activity-coupled low-load networks. |
| Scalar antenna gain | Cannot represent directionality, sector nulls, beam gain, or beam interference. |
| Analytical threshold profile | MCS operating points depend on the chosen margin and are not calibrated to a receiver. |
| No HARQ/control overhead detail | May overstate usable capacity and understate latency variance. |
| Static association | Omits handover interruption, ping-pong, and mobility-induced outage. |
| Application-payload queues | Omits protocol overhead and transport feedback. |

The direction of combined bias is not assumed; it is investigated with sensitivity cases and limited claims.

## 11. Profile promotion rule

A component moves from E0 to E1 when implemented with tests, to E2 only after independent reference evidence, and to E3 only after calibration against identified external data. A profile version changes whenever a numerical model, default, domain, or KPI definition changes in a way that can alter results.
