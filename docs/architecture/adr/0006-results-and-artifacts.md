# ADR-0006: Immutable, Schema-Versioned Run Bundles

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** KPI-001, EXP-005 through EXP-012, OPS-006, OPS-007

## Context

Unstructured text logs and manually copied plots cannot support reproducible conclusions. Results must preserve raw replication values, provenance, failures, and definitions without bloating source directories.

## Decision

Each run writes to a temporary directory and is atomically promoted to a content-addressed final bundle after checks succeed. A complete bundle contains:

- normalized scenario and experiment fragments;
- run identity, Git revision/dirty state, environment, RNG registry, and profile versions;
- structured warnings/failure record;
- tidy metric tables with schema and KPI-definition versions;
- optional semantic trace for debug/reference profiles;
- checksums and a completion marker.

Canonical JSON is the authoritative portable format for manifests, metadata, and the current metric
scale; CSV is presentation-only. A future columnar format requires a versioned, lossless schema
migration. Reporting reads saved bundles and writes derived analysis separately. Existing complete
run identities are immutable unless a deliberate force path records replacement.

## Consequences

- Results are independently inspectable and plots are reproducible.
- Schema migration becomes an explicit responsibility.
- Partial/failed writes cannot masquerade as complete runs.
- Large bundles remain outside Git and may be attached to releases or artifact storage.

## Rejected alternatives

- Plain text as the authoritative store: weak schema and parsing.
- Pickle: unsafe and Python-version coupled.
- One monolithic database: harder artifact portability and failure isolation.
- Plot directly from live memory: loses analysis provenance.
