from __future__ import annotations

import pytest

from nr_ran_sim.errors import InvariantViolation, RunExecutionError
from nr_ran_sim.kernel import (
    DeterministicKernel,
    EventKind,
    EventPhase,
    EventResult,
    create_scheduled_event,
)


def _result(event: object) -> EventResult:
    del event
    return EventResult.create("handled")


def test_same_tick_events_follow_phase_entity_and_sequence_order() -> None:
    specifications = [
        (EventPhase.OBSERVATION, "z", 0, EventKind.OBSERVATION),
        (EventPhase.PACKET_ARRIVAL, "b", 1, EventKind.PACKET_ARRIVAL),
        (EventPhase.PACKET_ARRIVAL, "a", 1, EventKind.PACKET_ARRIVAL),
        (EventPhase.PACKET_ARRIVAL, "a", 0, EventKind.PACKET_ARRIVAL),
        (EventPhase.PRIOR_SERVICE_COMPLETION, "z", 0, EventKind.SERVICE_COMPLETION),
        (EventPhase.DEADLINE_EXPIRATION, "z", 0, EventKind.PACKET_DEADLINE),
        (EventPhase.TOPOLOGY_CONTROL, "z", 0, EventKind.TOPOLOGY_CONTROL),
        (EventPhase.LINK_ASSOCIATION, "z", 0, EventKind.LINK_ASSOCIATION),
        (EventPhase.SCHEDULING, "z", 0, EventKind.SCHEDULING),
        (EventPhase.SERVICE_RESERVATION, "z", 0, EventKind.SERVICE_RESERVATION),
    ]
    kernel = DeterministicKernel()
    for kind in EventKind:
        kernel.register_handler(kind, _result)
    shuffled = list(reversed(specifications))
    for phase, entity, sequence, kind in shuffled:
        kernel.schedule(
            create_scheduled_event(
                tick=100,
                phase=phase,
                entity_key=entity,
                local_sequence=sequence,
                kind=kind,
            )
        )

    trace = kernel.run(100)

    observed = [(event.phase, event.entity_key, event.local_sequence) for event in trace.events]
    assert observed == sorted(observed)
    assert [event.phase for event in trace.events[:3]] == [10, 20, 30]


def test_trace_is_canonical_and_replayable() -> None:
    def execute() -> tuple[str, str]:
        kernel = DeterministicKernel()
        kernel.register_handler(
            EventKind.OBSERVATION,
            lambda event: EventResult.create(
                "observed", details={"entity": event.entity_key, "value": 7}
            ),
        )
        kernel.schedule(
            create_scheduled_event(
                tick=5,
                phase=EventPhase.OBSERVATION,
                entity_key="cell/a",
                local_sequence=0,
                kind=EventKind.OBSERVATION,
            )
        )
        trace = kernel.run(5)
        return trace.to_json(), trace.sha256

    assert execute() == execute()


def test_followup_may_use_a_later_phase_at_the_same_tick() -> None:
    kernel = DeterministicKernel()
    followup = create_scheduled_event(
        tick=10,
        phase=EventPhase.OBSERVATION,
        entity_key="bearer/a",
        local_sequence=0,
        kind=EventKind.OBSERVATION,
    )
    kernel.register_handler(
        EventKind.PACKET_ARRIVAL,
        lambda event: EventResult.create("arrival", followups=(followup,)),
    )
    kernel.register_handler(EventKind.OBSERVATION, _result)
    kernel.schedule(
        create_scheduled_event(
            tick=10,
            phase=EventPhase.PACKET_ARRIVAL,
            entity_key="bearer/a",
            local_sequence=0,
            kind=EventKind.PACKET_ARRIVAL,
        )
    )
    assert [event.phase for event in kernel.run(10).events] == [40, 80]


def test_duplicate_order_key_and_event_identity_are_rejected() -> None:
    kernel = DeterministicKernel()
    event = create_scheduled_event(
        tick=1,
        phase=EventPhase.OBSERVATION,
        entity_key="entity/a",
        local_sequence=0,
        kind=EventKind.OBSERVATION,
    )
    kernel.schedule(event)
    with pytest.raises(InvariantViolation, match="duplicated"):
        kernel.schedule(event)


def test_past_scheduling_and_nonmonotonic_stop_are_rejected() -> None:
    kernel = DeterministicKernel()
    kernel.run(10)
    past = create_scheduled_event(
        tick=9,
        phase=EventPhase.OBSERVATION,
        entity_key="entity/a",
        local_sequence=0,
        kind=EventKind.OBSERVATION,
    )
    with pytest.raises(InvariantViolation, match="earlier"):
        kernel.schedule(past)
    with pytest.raises(InvariantViolation, match="earlier"):
        kernel.run(9)


def test_missing_or_duplicate_handler_fails_closed() -> None:
    kernel = DeterministicKernel()
    kernel.register_handler(EventKind.OBSERVATION, _result)
    with pytest.raises(InvariantViolation, match="already"):
        kernel.register_handler(EventKind.OBSERVATION, _result)

    missing = DeterministicKernel()
    missing.schedule(
        create_scheduled_event(
            tick=0,
            phase=EventPhase.OBSERVATION,
            entity_key="entity/a",
            local_sequence=0,
            kind=EventKind.OBSERVATION,
        )
    )
    with pytest.raises(RunExecutionError, match="no registered handler"):
        missing.run(0)
