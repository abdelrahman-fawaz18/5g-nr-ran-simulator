# ADR-0008: Python Foundation and Continuous Quality Toolchain

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** CFG-001 through CFG-010, OPS-001 through OPS-010

## Context

The simulator requires strict scientific-input validation, explicit units, deterministic
serialization, cross-platform installation, and automated evidence. A broad framework would
increase dependency and security surface without improving the configuration boundary.

## Decision

- Support CPython 3.11, 3.12, and 3.13; CI exercises the oldest and newest supported minors on Windows and Linux.
- Use `uv` 0.12.3 and commit its universal `uv.lock`; CI installs with `--frozen`.
- Use the `src/` layout and Hatchling build backend.
- Use Pydantic 2 strict frozen models as the human configuration source of truth and generate JSON Schema from those models.
- Use Pint only at the authoring/normalization boundary. Runtime domain values are immutable canonical values and never carry unit strings.
- Use `yaml.safe_load` for YAML and the standard library for JSON, CLI parsing, hashing, and structured logging.
- Use canonical sorted JSON, Decimal string representation, and SHA-256 for scenario identity. Environment metadata is diagnostic and excluded from that digest.
- Use Ruff, strict mypy for the core package, pytest with branch coverage, Bandit, pip-audit, package builds, documentation-link checks, and a clean validation smoke command as mandatory CI gates.
- Pin third-party GitHub Actions to full immutable commit SHAs and grant read-only repository permissions.

## Consequences

- The runtime dependency surface is limited to Pydantic, Pint, and PyYAML.
- Configuration errors are rejected before runtime state is constructed and can be rendered as stable JSON.
- A dependency update is an intentional lockfile change with full CI evidence.
- Python 3.14 is not supported until the project's scientific and quality dependencies are reviewed together; silently widening the classifier is prohibited.
- NumPy is isolated to deterministic numerical and RNG functions; configuration parsing remains dependency-light.

## Rejected alternatives

- Hand-maintained JSON Schema plus dataclasses: risks two diverging input contracts.
- Unit suffixes in field names only: cannot prevent dimensionally invalid authoring values.
- Pint objects throughout the simulator: unnecessary inner-loop overhead and serialization complexity.
- Unlocked `pip install` in CI: weak environment reproducibility.
- Platform-only CI: misses path, newline, executable-entrypoint, and shell differences that affect a recruiter-facing package.
