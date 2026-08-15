# ADR-0009: Deterministic Mechanics and Packet Accounting

- **Status:** Accepted
- **Date:** 2026-08-13
- **Requirements:** SYS-003, SYS-005, SYS-007 through SYS-009, TIME-001 through TIME-009, MAC-009, QOS-001 through QOS-010, EXP-002 through EXP-004, EXP-006

## Context

ADR-0001 and ADR-0003 freeze event order and RNG derivation, but implementation still needs unambiguous identities, queue occupancy semantics, stochastic tick quantization, service injection, and a semantic replay boundary. Leaving these choices implicit would allow later radio and scheduler work to change packet outcomes without an intentional model revision.

## Decision

- Use type-distinct immutable IDs for cells, UEs, bearers, packets, events, and runs. Expand UE groups and bearers in lexical identifier plus integer-ordinal order.
- Store kernel events in a heap keyed only by `(integer_nanosecond_tick, phase, entity_key, local_sequence)`. Reject duplicate keys/IDs, past scheduling, missing handlers, and nonmonotonic processing.
- Keep the kernel policy-free. Mechanics tests may inject explicit service-completion grants, but
  grants must occur on configured slot boundaries. The capacity and scheduler layers own
  allocation decisions.
- Mutate one bearer queue only through typed arrival, service, deadline, failure, and censor commands. Queue payload occupancy is the sum of remaining bits; partial service frees bit capacity but the packet occupies one packet slot until terminal.
- Aggregate duplicate same-bearer/same-tick service grants before execution so caller ordering cannot change the trace.
- Quantize continuous inter-arrival draws to nanoseconds using Decimal half-to-even. An exponential draw that quantizes to zero becomes the minimum positive tick and increments a structured source diagnostic; it is never silent.
- Treat periodic plus constant packet size as the constant-bit-rate composition. Do not add a duplicate hard-coded CBR source type.
- Hash semantic traces, final packet snapshots, queue ledgers, seed records, and run identity. Keep platform/environment metadata and dirty-state diagnostics outside the semantic digest.

## Consequences

- Same-time packets cannot overwrite one another and all lifecycle outcomes remain traceable.
- Bit conservation includes active remaining bits, partial progress on active packets, completed payload, and original payload of terminally unsuccessful packets.
- Queue payload capacity represents remaining buffered work rather than immutable original packet size.
- The mechanics runner is verification infrastructure, not a radio-performance simulator;
  propagation, capacity, scheduling policy, and KPI conclusions belong to their dedicated layers.
- Changing semantic ID paths, event phases, quantization, queue occupancy, or seed namespaces is a numerical-behavior change requiring review.

## Rejected alternatives

- Float event times or mapping-keyed arrivals: equality/drift and collision risks.
- Insertion-order heap ties: declaration/refactor order could change outcomes.
- One global RNG or construction-order spawning: unrelated entities perturb existing samples.
- Silent zero-tick clipping: hides a quantization/model-domain event.
- Hard-coded application/CBR classes: duplicates configuration compositions and weakens experiment control.
