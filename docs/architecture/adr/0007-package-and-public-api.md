# ADR-0007: Layered Package with Schema-First Public Interface

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** SYS-005 through SYS-009, MAC-001, OPS-001 through OPS-003

## Context

A monolithic implementation would mix configuration, models, policy, state, logging, and output. Prematurely publishing Python classes would freeze implementation details before they are tested.

## Decision

Use the layered package in `../overview.md` with enforced one-way dependencies. The supported interface through the first release is:

- CLI commands;
- scenario/experiment schema versions;
- model-profile identifiers;
- result/run-bundle schemas.

Python modules are typed and independently testable but remain internal until a later API review. Scheduler, propagation, link, and metric components use small protocols/value objects rather than access to a shared mutable simulation object.

## Consequences

- Internal architecture can evolve without breaking users while data contracts stay stable.
- Dependency checks and explicit adapters add some boilerplate.
- Plugin-like policy/model replacement is possible without dynamic import complexity in Tier A.
- A public Python API, if needed, requires a separate ADR and compatibility policy.

## Rejected alternatives

- Refactor a monolithic prototype in place: preserves mixed responsibilities and hidden state.
- Framework-wide mutable context object: easy coupling and hard tests.
- Public class API immediately: premature compatibility burden.
- Microservices: deployment complexity without value for a local simulation engine.
