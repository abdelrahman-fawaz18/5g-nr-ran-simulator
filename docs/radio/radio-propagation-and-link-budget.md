# Radio Propagation and Link-Budget Model

| Field | Value |
| --- | --- |
| Model profile | `tier-a-fr1-static-v1` |
| Propagation source | 3GPP TR 38.901 V18.1.0, Tables 7.4.1-1 and 7.4.2-1 |
| Snapshot schema | `1.0` |
| Evidence boundary | Equation/reference verification, not measurement calibration |

## Capabilities

The radio-link layer turns deterministic mechanics into an inspectable static radio environment. A
scenario can now produce Cartesian cell/UE positions, every cell-to-UE propagation link,
long-term serving-cell association, and a complete wideband SINR budget.

The implementation is deliberately split into four independently testable layers:

1. `radio.geometry` computes explicit-metre 2D and 3D link geometry.
2. `radio.topology` expands explicit positions or bounded semantic-RNG placement.
3. `radio.propagation` evaluates the selected Release 18 path-loss row, LOS state, and
   optional static shadow fading.
4. `radio.link` computes total/PSD powers, receiver noise, interference, and SINR in linear
   watts before exporting logarithmic diagnostics.

`radio.snapshot` composes those layers into a transport-agnostic JSON scene. It is an
inspection artifact, not a second simulation engine.

The JSON boundary rounds binary64 results to 12 significant decimal digits before canonical
serialization and hashing. This retains substantially more resolution than the verification
tolerances while suppressing insignificant last-bit differences between operating-system math
libraries; in-memory calculations remain full precision.

## Why these boundaries matter

- Geometry errors cannot hide inside a path-loss function.
- Standards domains fail before logarithms or extrapolation; no input is clipped.
- One semantic RNG path owns each UE position, LOS draw, UMa environment-height draw, and
  shadow realization, so unrelated entities do not perturb an existing stream.
- Every received-power and SINR term is exported, allowing an engineer to reproduce the
  arithmetic independently.
- Presentation code consumes saved records and cannot silently change the radio model.

## Topology and geometry

The coordinate system is `local-cartesian`; all normalized coordinates and distances are in
metres. A UE group supports:

- `explicit`: one 3D position per UE ordinal;
- `uniform_rectangle`: independent seeded x/y placement inside closed configured bounds.

`minimum_2d_distance` applies between a candidate UE and every configured cell. Random
placement uses a finite per-UE `attempt_budget` and raises a structured run error when the
requested geometry is infeasible. Explicit positions are checked during normalization.

## Propagation scope and domains

The path-loss equations are reimplemented from the pinned
[ETSI TR 138 901 V18.1.0 PDF](https://www.etsi.org/deliver/etsi_tr/138900_138999/138901/18.01.00_60/tr_138901v180100p.pdf).
The project-wide Tier A carrier range narrows the source domain to 0.5-7.125 GHz.

| Scenario | BS height | UE height | LOS distance | NLOS distance | Extra inputs |
| --- | ---: | ---: | ---: | ---: | --- |
| RMa | 10-150 m | 1-10 m | 10 m-10 km | 10 m-5 km | Building height and street width, each 5-50 m |
| UMa | 25 m | 1.5-22.5 m | 10 m-5 km | 10 m-5 km | Per-link effective environment height from Note 1 |
| UMi street canyon | 10 m | 1.5-22.5 m | 10 m-5 km | 10 m-5 km | Effective environment height fixed at 1 m |

LOS equations are piecewise around the scenario breakpoint. Every NLOS row applies
`max(LOS path loss, candidate NLOS path loss)` exactly. Diagnostics retain both terms, the
chosen segment, breakpoint, distances, heights, carrier, source/model identifiers, and
`domain_status=inside`.

### LOS state and shadowing

`models.los_state` chooses one of two explicit behaviors:

- `explicit`: `explicit_link_states` supplies one LOS/NLOS entry for every cell and UE
  ordinal; no LOS draw occurs.
- `probability_static`: one seeded uniform draw per link is compared with the scenario's
  Table 7.4.2-1 LOS probability and remains fixed for the snapshot/run.

For UMa links with UE height above 13 m, Note 1 may require a separate seeded effective
environment-height choice. That realized value is exported because it changes the breakpoint.

`shadowing=independent_static` draws one zero-mean Gaussian dB value per link with the
scenario/state standard deviation from Table 7.4.1-1. `shadowing=off` exports zero dB. Neither
mode represents spatial or temporal correlation.

## Link budget, association, and SINR

The implemented downlink budget is:

```text
received dBm = transmit dBm + Tx gain dBi + Rx gain dBi
               - basic path loss dB - shadow dB - penetration dB - miscellaneous loss dB
```

Cell total power is spread uniformly over the resolved transmission bandwidth. The snapshot
exports total power and power spectral density at both transmitter and receiver. The Tier A
outdoor penetration default is 0 dB and is still explicit after normalization.

The association metric converts received PSD to power over one subcarrier bandwidth. Under
the Tier A uniform-PSD, scalar-gain abstraction this is the long-term reference-RE received
power used as the RSRP association proxy. It excludes fast fading and traffic load. An exact
tie selects the lexically smallest stable cell ID.

Thermal noise uses the versioned project assumption `-174 dBm/Hz`, resolved transmission
bandwidth, and UE noise figure. Two interference profiles are available:

- `noise_limited-v1`: interference is exactly zero;
- `full_buffer_reuse1-v1`: every non-serving cochannel cell transmits its configured total
  power uniformly across the full transmission bandwidth, independent of scheduler activity.

Interference watts are summed before conversion to dBm. SINR is then
`signal_w / (noise_w + interference_w)`. Exported total and component values allow exact
reconstruction.

## Generate a radio snapshot

```console
uv run nr-ran-sim radio-snapshot \
  examples/scenarios/uma-multicell-radio.yaml \
  --master-seed 0x11111111111111111111111111111111 \
  --replication-id 0 \
  --output artifacts/radio-snapshot.json \
  --quiet
```

The JSON contains:

- scene/model identity and semantic SHA-256;
- cell/UE coordinates and placement-attempt diagnostics;
- every cell-UE geometry, LOS decision, propagation term, and link budget;
- serving association, noise, individual interferers, aggregate interference, and SINR;
- the semantic RNG registry needed to audit stochastic inputs.

The file is collision-safe unless `--force` is explicit.

## Visualization path

The radio-link layer provides the stable static scene contract needed for a professional visualization:
cell/UE maps, serving-link overlays, LOS/NLOS styling, RSRP/SINR coloring, and drill-down link
budgets can all be rendered directly from saved JSON.

Animation is driven only by modeled temporal state: the dynamic-radio layer supplies mobility/channel-update frames and the experiment framework supplies
saved experiment metrics; reporting can combine both without plotting from live mutable state.
This keeps presentation downstream of verified
scientific records.

## Verification and limitations

Evidence includes independent clarity-first equation calculations, retained numeric vectors,
breakpoint/domain cases, LOS-probability cases, Gaussian/seed replay, analytical link/noise/
interference/SINR vectors, association ties, topology feasibility, and end-to-end snapshot
reconstruction.

This model does not implement fast fading, spatially correlated shadowing, penetration models,
antenna patterns/beamforming, activity-coupled interference, link adaptation, scheduling, or
measurement calibration. Its correct claim is: the documented Release 18 equations are
implemented and reference-checked over the stated Tier A domain.
