# Quality and Evidence Policy

## Purpose

This policy prevents polished documentation from outrunning the simulator's actual fidelity. It applies to code, models, experiments, plots, README statements, release notes, portfolio descriptions, and resume bullets.

## Evidence levels

| Level | Meaning | Permitted wording |
| --- | --- | --- |
| E0 — Proposed | Idea is documented but not implemented | “Proposed” or “targeted” |
| E1 — Implemented | Code exists and local tests exercise behavior | “Implements the documented abstraction” |
| E2 — Verified | Independent analytical or tabulated checks pass | “Verified against [named reference] within [tolerance]” |
| E3 — Calibrated | Parameters were fitted or adjusted against independent data | “Calibrated against [dataset/tool] for [domain]” |
| E4 — Experimentally supported | A reproducible multi-run study supports a scoped conclusion | “In the documented scenario, the experiment found…” |

Implementation tests written from the same formula do not alone qualify as independent verification.

## Standards-derived model requirements

A standards-derived model is not complete until its record includes:

- exact document release/version and date;
- clause, equation, or table;
- supported domain, variables, and units;
- interpretation, approximations, and deviations;
- implementation location;
- independent reference vector and tolerance;
- behavior outside the supported domain.

## Experiment evidence requirements

Every result used in documentation must trace to a saved experiment manifest and contain:

- code revision and clean/dirty state;
- normalized configuration and configuration hash;
- master seed and replication/stream identifiers;
- environment and dependency versions;
- run duration, warm-up, and failed-run policy;
- raw per-run metrics and aggregation method;
- uncertainty measure for stochastic comparisons;
- warnings, exclusions, and domain violations.

A single stochastic run may illustrate mechanics but cannot support a general performance conclusion.

## Plot and table rules

- Generate plots from saved machine-readable results.
- Label axes with quantities and units.
- Show sample count and uncertainty where the analysis is stochastic.
- Do not truncate axes or choose filters in a way that changes the conclusion without disclosure.
- Keep failed and excluded replications auditable.
- Include a caption stating scenario scope and the artifact or manifest identifier.

## Claim review checklist

Before adding a headline claim to the README, portfolio, or resume, confirm:

- the claim has an E-level appropriate to its wording;
- the evidence is committed, released, or durably linked;
- the scenario and fidelity boundary are stated;
- the metric definition is unambiguous;
- uncertainty and comparison controls are appropriate;
- no statement implies real-network validation, full standard compliance, or production adoption without such evidence.

## Generated and assisted work

AI assistance may support planning, implementation, test design, and documentation. The project owner remains responsible for technical review, source verification, test adequacy, and final claims. Generated text or code does not substitute for an independent validation oracle.

## Exceptions

An exception must be documented in docs/DECISIONS.md with its scope, risk, expiry/review condition, and effect on permissible claims.
