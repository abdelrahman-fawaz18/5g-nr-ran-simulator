# ADR-0017: Verified evidence publication boundary

- **Status:** Accepted
- **Date:** 2026-08-14

## Context

The flagship's complete unpacked bundle is 2.63 GiB, while ordinary source review needs the
manifest, summary, uncertainty, plots, and lineage rather than 360 large run traces. Presentation
assets must not become an unreviewed analysis implementation.

## Decision

The complete bundle is a compressed, checksummed release asset. Source control contains a compact
evidence snapshot created only after the verifier checks the completion marker, bundle digest,
every source-run checksum, 5,040 metric-row digests and lineage links, the summary, the plot
manifest, all plots, completeness, and common-random-number pairing.

Recruiter-facing static visuals are generated deterministically from that snapshot. They may
select and format existing estimates/comparisons but cannot run simulations, recompute KPIs or
bootstrap intervals, filter source replications, or edit results. The repository is licensed under
the MIT License.

## Consequences

- A reviewer gets a fast, inspectable evidence path while the complete source records remain
  available for deep audit.
- Visual regressions fail when evidence digests or expected counts diverge.
- The Python sdist explicitly excludes evidence and generated run data; those surfaces have
  separate distribution roles.
- Repository visuals remain compact, inspectable, and linked to the verified saved summary.
