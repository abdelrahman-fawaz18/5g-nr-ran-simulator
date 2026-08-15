# ADR-0016: Preregistered heterogeneous-QoS flagship study

- **Status:** Accepted
- **Date:** 2026-08-14

## Context

The release needs one technically meaningful study that exercises the verified simulator without
claiming calibration. Selecting metrics or conditions after observing outcomes would weaken the
credibility of the portfolio evidence. A separate presentation implementation risks disconnecting results from source
data unless its lineage is fixed.

## Decision

The flagship is the 360-run static-FR1 scheduler study frozen in
`docs/experiments/scheduler-performance-study-protocol.md`. It compares Round Robin, Max-C/I, and
Proportional Fair under four broadband loads while a deadline-bearing low-latency class remains
fixed. Thirty common-random-number replications are used per variant. The hypotheses, primary
outcomes, confidence method, reference scheduler, acceptance checks, and interpretation rules are
frozen before execution.

The complete generated bundle remains a release artifact because individual run files are too
large for ordinary source control. A compact evidence snapshot may be committed only when every
value traces to the bundle and its checksums. Static evidence views consume that snapshot and are not a
second analysis implementation.

## Consequences

- Scheduler conclusions are bounded to the exact Tier A model and experiment domain.
- Results that contradict the hypotheses remain reportable evidence.
- Changing the design after execution requires an explicitly versioned new study.
- Recruiters can inspect the protocol independently of the result narrative.
- Public visibility remains a separate owner decision.
