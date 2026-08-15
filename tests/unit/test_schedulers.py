from __future__ import annotations

from decimal import Decimal

import pytest

from nr_ran_sim.errors import InvariantViolation
from nr_ran_sim.mac import (
    AllocationDecision,
    MaxCiScheduler,
    PrbAllocation,
    ProportionalFairScheduler,
    RoundRobinScheduler,
    SchedulerObservation,
    SchedulingCandidate,
    ServiceFeedback,
    validate_decision,
)


def _candidate(ue_id: str, payload: int, rate: int | None = None) -> SchedulingCandidate:
    return SchedulingCandidate(
        ue_id=ue_id,
        queue_payload_bits=10_000,
        achievable_payload_bits=payload,
        achievable_rate_bps=payload if rate is None else rate,
        sinr_db=10.0,
    )


def _observation(*candidates: SchedulingCandidate, prbs: int = 8, tick: int = 0):
    return SchedulerObservation(  # type: ignore[no-untyped-def]
        tick=tick,
        interval_ns=1_000_000_000,
        cell_id="cell/a",
        available_prbs=prbs,
        candidates=tuple(candidates),
    )


def _allocations(decision: AllocationDecision) -> dict[str, int]:
    return {item.ue_id: item.prbs for item in decision.allocations}


def test_round_robin_splits_prbs_and_rotates_remainder_without_channel_ranking() -> None:
    scheduler = RoundRobinScheduler()
    observation = _observation(
        _candidate("ue/a", 1),
        _candidate("ue/b", 1_000_000),
        _candidate("ue/c", 10),
    )

    first = scheduler.decide(observation)
    second = scheduler.decide(_observation(*observation.candidates, tick=1_000_000_000))

    assert _allocations(first) == {"ue/a": 3, "ue/b": 3, "ue/c": 2}
    assert _allocations(second) == {"ue/a": 2, "ue/b": 3, "ue/c": 3}
    assert dict(first.diagnostics)["rotated_order"] == "ue/a,ue/b,ue/c"
    assert dict(second.state)["cursor/cell/a"] == "2"


def test_round_robin_handles_more_ues_than_prbs_and_empty_observation() -> None:
    scheduler = RoundRobinScheduler()
    decision = scheduler.decide(
        _observation(_candidate("ue/a", 1), _candidate("ue/b", 2), _candidate("ue/c", 3), prbs=2)
    )
    assert _allocations(decision) == {"ue/a": 1, "ue/b": 1}
    empty = scheduler.decide(_observation(prbs=2, tick=1))
    assert empty.allocations == ()


def test_max_ci_uses_full_allocation_payload_and_lexical_tie_break() -> None:
    scheduler = MaxCiScheduler()
    decision = scheduler.decide(
        _observation(
            _candidate("ue/a", 200),
            _candidate("ue/b", 100),
            _candidate("ue/c", 200),
        )
    )
    assert decision.allocations == (PrbAllocation("ue/a", 8),)
    assert dict(decision.diagnostics)["ranking_metric"] == (
        "full-allocation-transport-payload-bits"
    )
    assert scheduler.state() == ()


def test_proportional_fair_uses_ewma_served_rate_and_updates_zero_service_candidates() -> None:
    scheduler = ProportionalFairScheduler(Decimal("0.5"), Decimal("100"))
    observation = _observation(
        _candidate("ue/a", 1000, 1000),
        _candidate("ue/b", 500, 500),
    )
    first = scheduler.decide(observation)
    assert first.allocations == (PrbAllocation("ue/a", 8),)

    scheduler.record_service(
        ServiceFeedback(
            cell_id="cell/a",
            completion_tick=1_000_000_000,
            interval_ns=1_000_000_000,
            eligible_ue_ids=("ue/a", "ue/b"),
            served_bits=(("ue/a", 1000),),
        )
    )
    state = dict(scheduler.state())
    assert state["average_rate_bps/cell/a/ue/a"] == "550"
    assert state["average_rate_bps/cell/a/ue/b"] == "50"
    second = scheduler.decide(_observation(*observation.candidates, tick=1_000_000_000))
    assert second.allocations == (PrbAllocation("ue/b", 8),)


def test_decision_validator_rejects_ineligible_duplicate_noninteger_and_excess() -> None:
    observation = _observation(_candidate("ue/a", 1), prbs=4)

    def decision(*allocations: PrbAllocation) -> AllocationDecision:
        return AllocationDecision("bad", 0, "cell/a", allocations, (), ())

    with pytest.raises(InvariantViolation, match="ineligible"):
        validate_decision(observation, decision(PrbAllocation("ue/b", 1)))
    with pytest.raises(InvariantViolation, match="unique"):
        validate_decision(
            observation,
            decision(PrbAllocation("ue/a", 1), PrbAllocation("ue/a", 1)),
        )
    with pytest.raises(InvariantViolation, match="positive integer"):
        validate_decision(observation, decision(PrbAllocation("ue/a", 0)))
    with pytest.raises(InvariantViolation, match="exceeds"):
        validate_decision(observation, decision(PrbAllocation("ue/a", 5)))


def test_scheduler_contract_models_fail_closed() -> None:
    with pytest.raises(InvariantViolation):
        _candidate("", 1)
    with pytest.raises(InvariantViolation):
        SchedulerObservation(0, 1, "cell/a", 1, (_candidate("ue/b", 1), _candidate("ue/a", 1)))
    with pytest.raises(InvariantViolation):
        ProportionalFairScheduler(Decimal(0), Decimal(1))
    with pytest.raises(InvariantViolation):
        ServiceFeedback("cell/a", 1, 1, ("ue/a",), (("ue/b", 1),))
