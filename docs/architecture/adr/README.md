# Architecture Decision Records

Accepted engineering decisions:

| ADR | Decision |
| --- | --- |
| [ADR-0001](0001-hybrid-slot-event-kernel.md) | Hybrid arbitrary-event / slot-boundary kernel and exact same-time ordering |
| [ADR-0002](0002-units-and-validation.md) | Explicit unit objects, canonical SI boundary, fail-closed validation |
| [ADR-0003](0003-deterministic-randomness.md) | Semantic, order-independent RNG streams and paired comparisons |
| [ADR-0004](0004-link-adaptation-abstraction.md) | Honest analytical CQI/MCS profile with required implementation margin |
| [ADR-0005](0005-interference-fidelity.md) | Noise-limited and full-buffer Tier A; activity coupling deferred |
| [ADR-0006](0006-results-and-artifacts.md) | Immutable, schema-versioned, content-addressed run bundles |
| [ADR-0007](0007-package-and-public-api.md) | Layered package and schema-first public interface |
| [ADR-0008](0008-python-foundation-and-quality-toolchain.md) | Python foundation and continuous quality toolchain |
| [ADR-0009](0009-deterministic-mechanics-and-packet-accounting.md) | Stable identities, deterministic mechanics, queue accounting, and stochastic tick quantization |
| [ADR-0010](0010-static-radio-state-and-snapshot.md) | Reconstructable static radio state and a versioned visualization-ready snapshot contract |
| [ADR-0011](0011-resource-capacity-and-inspection-boundary.md) | Exact resource/TBS accounting and a non-summable capacity-inspection boundary |
| [ADR-0012](0012-scheduler-service-and-kpi-pipeline.md) | Scheduler decisions, reserved queue service, paired exogenous identity, and KPI reducers |
| [ADR-0013](0013-dynamic-radio-causality-and-fr2-boundary.md) | Causal activity interference, dynamic channel/handover state, and bounded FR2 availability |
| [ADR-0014](0014-reproducible-experiment-and-saved-reporting.md) | Deterministic experiment designs, paired bootstrap analysis, and saved-data-only reporting |
| [ADR-0015](0015-validation-and-performance-evidence.md) | Deterministic property tests, independent cross-checks, approved regressions, and measured performance budgets |
| [ADR-0016](0016-preregistered-flagship-study.md) | Preregistered heterogeneous-QoS flagship design and evidence-publication boundary |
| [ADR-0017](0017-verification-publication-and-private-release.md) | Full-bundle verification, compact evidence, and static publication boundary |

An ADR is immutable once accepted except for status annotations and typo corrections. A changed decision receives a new ADR that explicitly supersedes the old one.
