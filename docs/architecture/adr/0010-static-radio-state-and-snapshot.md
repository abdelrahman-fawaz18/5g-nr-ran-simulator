# ADR-0010: Reconstructable Static Radio State and Visualization Contract

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** PROP-001 through PROP-011; LINK-001 through LINK-006; SYS-003, SYS-008

## Context

The radio-link layer must provide radio inputs that are scientifically inspectable and reusable by
scheduling, experiment, and visualization layers. Coupling model evaluation directly to a
presentation layer would create a second behavior path, while waiting until final presentation would
risk discovering that important diagnostics were never retained.

## Decision

- Build immutable typed topology, propagation, link-budget, noise, interference, association,
  and SINR records.
- Evaluate and retain every configured cell-to-UE link before association.
- Associate by maximum long-term power over one subcarrier bandwidth under the Tier A
  uniform-PSD abstraction; break exact ties by stable lexical cell ID.
- Keep all power addition/division in linear watts and export both linear/logarithmic values.
- Publish a versioned `radio-snapshot` JSON contract with canonical semantic SHA-256 and RNG
  provenance.
- Keep snapshots transport- and presentation-agnostic. Reporting code may read them
  but radio models never import visualization or reporting code.
- Add time-varying frames only with the later mobility/channel-state contract. Do not imply
  animation by duplicating static records.

## Consequences

- A reviewer can reconstruct each received power and SINR without reading internal state.
- Static maps and diagnostic explorers can be built now; trustworthy animation waits for real
  temporal state.
- Snapshot-schema changes require compatibility review and regression evidence.
- Full all-cell link retention increases artifact size but is appropriate for static radio
  inspection; the experiment framework supports compact derived evidence for large studies.

## Rejected alternatives

- Plot directly from live model objects: presentation cannot be reproduced from saved data.
- Export serving links only: association and interference cannot be independently audited.
- Build a presentation UI first: interface work would precede scheduler, mobility, and metric schemas.
- Store only dB terms: interference summation and dimensional correctness become opaque.
