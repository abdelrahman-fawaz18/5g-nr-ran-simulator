# ADR-0004: Explicit Analytical Link-Adaptation Profile

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** LINK-009 through LINK-014

## Context

3GPP TS 38.214 specifies MCS/CQI parameters and target error behavior, but not a universal receiver SINR-to-CQI threshold table. Adopting unexplained thresholds would create false precision. Building calibrated EESM/BLER curves is a separate link-level effort with dataset and licensing implications.

## Decision

Tier A uses `analytical-awgn-gap-v1`:

- one layer, one codeword, MCS/CQI Table 1 family;
- CQI threshold derived from CQI Table 1 spectral efficiency `eta`: `10 log10(2^eta − 1) + implementation_margin_dB`;
- `implementation_margin_dB` is required in every scenario and has no hidden default;
- highest CQI threshold met wins; below the lowest is outage;
- the service MCS is the highest MCS Table 1 entry whose efficiency does not exceed the selected CQI efficiency;
- TBS follows the supported TS 38.214 Clause 5.1.3.2 procedure;
- target transport-block error probability metadata is 0.1 for Table 1;
- capacity is modeled without calibrated BLER sampling, HARQ timing, or combining.

The profile is labeled analytical and uncalibrated in manifests and reports. Flagship conclusions require margin sensitivity cases.

A future calibrated profile must have versioned curve provenance, supported MCS/resource/channel domains, license review, and independent verification. It receives a new profile identifier and does not overwrite Tier A behavior.

## Consequences

- The implemented mapping is transparent, monotonic, and testable.
- Absolute throughput is margin-sensitive and cannot be presented as receiver prediction.
- Scheduler comparisons remain useful when the model is held fixed and sensitivity is reported.
- PHY packet error/retransmission conclusions are outside Tier A.

## Rejected alternatives

- Unproven path-loss-to-CQI thresholds: omit power/noise/interference and lack provenance.
- Treat Shannon capacity as calibrated performance: unsupported claim.
- Copy third-party BLER tables immediately: provenance/license/fidelity mismatch.
- Defer all link adaptation: blocks scheduler/capacity integration without improving honesty.
