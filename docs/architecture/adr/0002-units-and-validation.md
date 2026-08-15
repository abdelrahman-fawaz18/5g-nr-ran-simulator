# ADR-0002: Explicit Units and Fail-Closed Validation

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** CFG-001 through CFG-010

## Context

Wireless simulations routinely mix GHz/Hz, MHz/kHz, dBm/watts, dB/linear ratios, metres/kilometres, and milliseconds/seconds. Comments are not sufficient protection against plausible unit mistakes.

## Decision

- Human-authored physical values use `{value, unit}` objects.
- The configuration layer uses a units library at the parsing/normalization boundary and typed immutable domain records afterward.
- Canonical internal bases are metre, second/tick, hertz, watt, bit, and dimensionless linear ratio.
- Time is stored as integer nanoseconds after exact decimal conversion.
- Log quantities retain distinct types: dB for ratios/losses, dBm for absolute power, dBi for antenna gain.
- Unknown fields and unsupported units are rejected.
- No scientifically meaningful default remains implicit after normalization.
- Normalized manifests emit explicit defaults and a SHA-256 digest.
- Cross-field standards domains are validated before constructing runtime state.

The unit library does not remain in performance-critical inner-loop values; conversion is once at the boundary.

## Consequences

- Manifests are more verbose but self-describing.
- Values can be authored in convenient units without weakening internal consistency.
- Log/linear conversion must use explicit functions and tests.
- A unit-library version becomes part of the environment record.

## Rejected alternatives

- Unit suffixes embedded only in field names: fixed units and easy copy errors.
- Unit strings such as `3.5 GHz`: convenient but harder to validate and diff canonically.
- Unit-aware objects everywhere: safety with unacceptable inner-loop overhead and serialization complexity.
