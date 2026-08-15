# Scenario Schema Design

| Field | Value |
| --- | --- |
| Contract version | 1.0 design baseline |
| Serialization | YAML or JSON input; canonical JSON normalization |
| Implementation | Strict typed models with generated JSON Schema |
| Unknown fields | Rejected |

## 1. Design principles

- Every scientific input is explicit after normalization.
- Physical values are `{value, unit}` objects.
- Human input and normalized canonical output are distinct artifacts.
- Structural validation precedes unit conversion; semantic/standards validation follows it.
- IDs are lowercase ASCII slugs matching `^[a-z][a-z0-9-]{0,63}$`.
- Collections with identity are keyed by ID in canonical form to avoid order-dependent behavior.
- Defaults are allowed only when documented here and emitted in canonical output.

## 2. Tier A example

```yaml
schema_version: "1.0"
scenario_id: uma-fr1-mixed-load
description: Static UMa scheduler comparison baseline

simulation:
  warmup: {value: 100, unit: ms}
  measurement: {value: 1000, unit: ms}
  drain: {value: 300, unit: ms}

radio:
  direction: downlink
  frequency_range: FR1
  carrier_frequency: {value: 3.5, unit: GHz}
  channel_bandwidth: {value: 100, unit: MHz}
  subcarrier_spacing: {value: 30, unit: kHz}
  cyclic_prefix: normal
  layers: 1
  cqi_table: table1
  mcs_table: table1
  target_bler: 0.1
  implementation_margin: {value: 3.0, unit: dB}
  data_re_overhead_fraction: 0.14

models:
  fidelity_profile: tier-a-fr1-static-v1
  propagation: 3gpp-tr38901-r18-v18.1.0
  los_state: probability_static
  shadowing: independent_static
  interference: full-buffer-reuse1-v1
  link_adaptation: analytical-awgn-gap-v1

topology:
  scenario: uma
  coordinate_system: local-cartesian
  cells:
    cell-a:
      position:
        x: {value: 0, unit: m}
        y: {value: 0, unit: m}
        z: {value: 25, unit: m}
      transmit_power: {value: 46, unit: dBm}
      antenna_gain: {value: 0, unit: dBi}
      miscellaneous_loss: {value: 0, unit: dB}
  ue_groups:
    users:
      count: 20
      placement:
        mode: uniform_rectangle
        x_min: {value: 35, unit: m}
        x_max: {value: 500, unit: m}
        y_min: {value: -250, unit: m}
        y_max: {value: 250, unit: m}
        height: {value: 1.5, unit: m}
      receiver_noise_figure: {value: 7, unit: dB}
      antenna_gain: {value: 0, unit: dBi}
      bearers: [broadband]

traffic_profiles:
  broadband:
    source:
      type: poisson
      mean_interarrival: {value: 2, unit: ms}
    packet_size:
      type: constant
      payload: {value: 12000, unit: bit}
    queue:
      max_packets: 1000
      max_payload: {value: 12000000, unit: bit}
    deadline: null

scheduler:
  policy: proportional-fair
  parameters:
    averaging_alpha: 0.01
    initial_rate_floor: {value: 1, unit: kbit/s}
```

This example is structural, not an approved experiment or calibrated radio profile.

## 3. Top-level object contract

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `schema_version` | string | Yes | Exactly a supported semantic version. |
| `scenario_id` | ID | Yes | Stable within an experiment. |
| `description` | string | Yes | Nonempty, max 500 characters. |
| `simulation` | object | Yes | Warm-up, measurement, and drain durations. |
| `radio` | object | Yes | Tier A FR1 radio configuration. |
| `models` | object | Yes | Exact profile identifiers. |
| `topology` | object | Yes | Scenario, cells, UE groups. |
| `traffic_profiles` | map | Yes | At least one profile referenced by a UE group. |
| `scheduler` | object | Yes | One policy per normalized run. Experiment sweeps expand alternatives. |
| `extensions` | object | No | Namespaced experimental fields; empty by default. |

## 4. Quantity types

| Dimension | Accepted authoring units | Canonical form |
| --- | --- | --- |
| Time | `ns`, `us`, `ms`, `s` | integer ns plus SI seconds for reporting |
| Frequency | `Hz`, `kHz`, `MHz`, `GHz` | integer/decimal Hz |
| Distance | `mm`, `cm`, `m`, `km` | metre |
| Absolute power | `W`, `mW`, `dBm` | watt plus explicit dBm diagnostic |
| Relative gain/loss | `dB`, `dBi` as appropriate | typed logarithmic value |
| Data | `bit`, `kbit`, `Mbit` | integer bit; decimal prefix |
| Rate | `bit/s`, `kbit/s`, `Mbit/s` | bit/s |

Fractional bits and negative linear powers are invalid. Unit conversion from decimal authoring values must not pass through binary float before time quantization.

## 5. Structural types

### Simulation

- `warmup`, `measurement`, `drain`: nonnegative time; measurement strictly positive.
- Total stop tick must fit the supported integer range.
- Drain must cover the maximum deadline when deadline-success claims are enabled, or validation emits a structured scientific warning that the experiment must explicitly acknowledge.

The experiment manifest, not the scientific scenario, carries the 128-bit `master_seed`, replication index, sweep definition, and execution metadata. This separation allows one normalized scenario to be replayed under multiple declared replications without mutating its scientific identity.

### Radio

- `direction=downlink`, `frequency_range=FR1`, `cyclic_prefix=normal`, `layers=1` in Tier A.
- Carrier 0.5–7.125 GHz and within the selected propagation row.
- SCS one of 15/30/60 kHz.
- Bandwidth/SCS pair must exist in pinned TS 38.104 Table 5.3.2-1.
- `cqi_table=table1`, `mcs_table=table1`, target BLER exactly 0.1 for baseline profile.
- Implementation margin is required and finite.
- Overhead fraction in `[0,1)`.

### Models

All profile fields are closed enumerations. A profile change affects run identity. `probability_static` requires a LOS RNG stream; `explicit` requires per-link state. `independent_static` shadowing is incompatible with a claim of spatial consistency.

### Topology

- Scenario: `rma`, `uma`, or `umi_street_canyon`.
- At least one cell and one UE.
- `placement.mode=explicit` supplies exactly one 3D position per UE ordinal;
  `uniform_rectangle` supplies finite ordered bounds, height, minimum cell distance, and a
  bounded attempt budget.
- Cell and UE heights/distances must satisfy selected model domain.
- `uniform_rectangle` requires ordered finite bounds and a feasible minimum-distance constraint.
- RMa requires explicit average building height and average street width in the 5-50 m domain;
  those environment fields are rejected for UMa/UMi.
- `models.los_state=explicit` requires one `explicit_link_states` entry per configured cell and
  one state per UE ordinal. Probability mode rejects those unused values.
- UE `penetration_loss` defaults to the documented outdoor value of 0 dB and is explicit in the
  normalized manifest.
- UE groups reference existing traffic profile IDs.

### Traffic

- Source types and packet-size types follow the Traffic/QoS contract.
- Bounds are ordered and strictly positive.
- Queue defines at least one finite capacity for recruiter-facing experiments; unbounded queues require an explicit research justification.
- Deadline is null or strictly positive.
- Optional `qos_reference_5qi` never populates other fields.

### Scheduler

- Policy enumeration: `round-robin`, `max-ci`, `proportional-fair`.
- Round Robin and Max-C/I accept no hidden tuning fields.
- PF requires `averaging_alpha` in `(0,1]` and positive initial rate floor.
- Unknown policy parameters fail validation.

## 6. Canonical normalization

Normalization performs:

1. Unicode/ID validation and deterministic key ordering;
2. default expansion;
3. exact unit conversion;
4. standards-domain and cross-reference validation;
5. resolved PRB count, numerology index, slot duration, and transmission bandwidth insertion;
6. model/source profile version insertion;
7. canonical JSON serialization with defined number representation;
8. SHA-256 digest calculation.

Derived fields cannot be supplied by the user; doing so is rejected to prevent disagreement with the resolver.

## 7. Generated JSON Schema

The configuration layer implements strict typed models and generates `schemas/scenario.schema.json`.
Hand-edited JSON Schema does not become a second source of truth. Semantic rules that JSON Schema
cannot express remain in the validator and are enumerated as requirement-linked checks.

## 8. Compatibility policy

- Patch schema releases clarify documentation without changing normalized meaning.
- Minor releases add backward-compatible optional input that normalizes explicitly.
- Major releases may change required fields or semantics and require a migration tool or clear manual migration notes.
- Results always record both input schema and normalized model-profile versions.
