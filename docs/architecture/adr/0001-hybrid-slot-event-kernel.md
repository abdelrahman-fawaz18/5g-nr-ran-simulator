# ADR-0001: Hybrid Slot/Event Simulation Kernel

- **Status:** Accepted
- **Date:** 2026-08-13
- **Decision owners:** Project engineering baseline
- **Requirements:** TIME-001 through TIME-009

## Context

A pure fixed-step loop makes asynchronous packet deadlines/arrivals inefficient and encourages float-keyed dictionaries. A general discrete-event kernel alone can obscure the slot boundaries at which NR resource allocation occurs.

## Decision

Use a hybrid kernel:

- integer nanosecond ticks for all event time;
- arbitrary-time exogenous events for arrivals, deadlines, and later mobility/control changes;
- scheduling and radio service once per configured normal-CP slot in Tier A;
- priority key `(tick, phase_priority, entity_key, local_sequence)`;
- stable same-tick phases:
  1. finish prior-slot service and emit completions;
  2. expire unfinished packets with deadline at the tick;
  3. apply topology/control changes effective at the tick;
  4. enqueue packet arrivals stamped at the tick;
  5. update link state and association for the next interval;
  6. build scheduler observation and obtain allocation;
  7. reserve service and schedule its result at the next slot boundary;
  8. emit nonmutating observations.

An arrival at a slot boundary is eligible immediately. An arrival between boundaries waits until the next scheduling boundary. A service completion at the exact deadline succeeds because completion precedes expiration.

## Consequences

- Slot mechanics remain explicit while sparse traffic events avoid unnecessary per-UE polling.
- Event order is testable and independent of Python container order.
- Mini-slot or multi-numerology scheduling requires a later profile/ADR extension.
- Service capacity is committed over an interval and realized at its end, which must be reflected in latency definitions.

## Rejected alternatives

- **Floating fixed-step loop:** drift and ambiguous equality.
- **Pure arbitrary event service:** weakens NR slot semantics and policy comparability.
- **One event phase:** cannot define exact deadline/arrival/completion boundaries.
