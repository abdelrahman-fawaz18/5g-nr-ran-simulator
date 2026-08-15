from __future__ import annotations

import pytest

from nr_ran_sim.domain import (
    BearerId,
    BearerRecord,
    PacketCohort,
    PacketId,
    PacketRecord,
    TerminalCause,
    UeId,
)
from nr_ran_sim.errors import InvariantViolation
from nr_ran_sim.traffic import (
    ApplyService,
    BearerQueue,
    CensorQueue,
    EnqueuePacket,
    ExpirePacket,
    FailPacket,
    ServiceResult,
)

BEARER = BearerRecord(
    id=BearerId("bearer/users/000000/test"),
    ue_id=UeId("ue/users/000000"),
    traffic_profile_id="test",
)


def _packet(
    ordinal: int,
    *,
    arrival: int = 0,
    payload: int = 1000,
    deadline: int | None = None,
) -> PacketRecord:
    return PacketRecord(
        id=PacketId(f"packet/bearer/users/000000/test/{ordinal:012d}"),
        bearer_id=BEARER.id,
        arrival_tick=arrival,
        payload_bits=payload,
        deadline_tick=deadline,
        cohort=PacketCohort.MEASUREMENT,
    )


def _queue(*, max_packets: int | None = 10, max_bits: int | None = 10_000) -> BearerQueue:
    return BearerQueue(BEARER, max_packets=max_packets, max_payload_bits=max_bits)


def test_reference_vector_partial_service_preserves_identity_and_bits() -> None:
    queue = _queue()
    packet = _packet(0)
    queue.apply(EnqueuePacket(0, packet))

    results = [
        queue.apply(ApplyService(10, 300)),
        queue.apply(ApplyService(20, 400)),
        queue.apply(ApplyService(30, 300)),
    ]

    assert all(isinstance(result, ServiceResult) for result in results)
    assert [result.consumed_bits for result in results if isinstance(result, ServiceResult)] == [
        300,
        400,
        300,
    ]
    snapshot = queue.snapshots()[0]
    assert snapshot.packet.id == packet.id
    assert snapshot.first_service_tick == 10
    assert snapshot.completion_tick == 30
    assert snapshot.remaining_bits == 0
    assert snapshot.terminal_cause is TerminalCause.COMPLETED
    ledger = queue.ledger()
    assert ledger.offered_bits == ledger.completed_payload_bits == 1000
    assert ledger.service_consumed_bits == 1000


def test_fifo_service_can_complete_one_packet_and_partially_serve_next() -> None:
    queue = _queue()
    first = _packet(0, payload=100)
    second = _packet(1, payload=100)
    queue.apply(EnqueuePacket(0, first))
    queue.apply(EnqueuePacket(0, second))

    result = queue.apply(ApplyService(5, 150))

    assert isinstance(result, ServiceResult)
    assert [event.packet_id for event in result.events] == [first.id, second.id]
    assert queue.queued_packet_count == 1
    assert queue.queued_payload_bits == 50
    assert queue.snapshots()[1].remaining_bits == 50


def test_completion_at_exact_deadline_wins_before_expiration() -> None:
    queue = _queue()
    packet = _packet(0, payload=100, deadline=100)
    queue.apply(EnqueuePacket(0, packet))
    completed = queue.apply(ApplyService(100, 100))
    expired = queue.apply(ExpirePacket(100, packet.id))

    assert isinstance(completed, ServiceResult)
    assert completed.events[0].terminal_cause is TerminalCause.COMPLETED
    assert expired == ()
    assert queue.snapshots()[0].terminal_cause is TerminalCause.COMPLETED


def test_packet_and_bit_capacity_boundaries_tail_drop_whole_packet() -> None:
    queue = _queue(max_packets=2, max_bits=150)
    first = _packet(0, payload=100)
    second = _packet(1, payload=50)
    overflow = _packet(2, payload=1)
    queue.apply(EnqueuePacket(0, first))
    queue.apply(EnqueuePacket(0, second))
    events = queue.apply(EnqueuePacket(0, overflow))

    assert not isinstance(events, ServiceResult)
    assert events[-1].terminal_cause is TerminalCause.OVERFLOW_DROP
    assert queue.queued_payload_bits == 150
    assert queue.snapshots()[-1].remaining_bits == 1
    ledger = queue.ledger()
    assert ledger.terminal_packets == 1
    assert ledger.terminal_payload_bits == 1


def test_partial_packet_can_expire_and_conservation_still_reconciles() -> None:
    queue = _queue()
    packet = _packet(0, payload=100, deadline=20)
    queue.apply(EnqueuePacket(0, packet))
    queue.apply(ApplyService(10, 40))
    events = queue.apply(ExpirePacket(20, packet.id))

    assert not isinstance(events, ServiceResult)
    assert events[0].affected_bits == 60
    assert events[0].terminal_cause is TerminalCause.DEADLINE_EXPIRED
    snapshot = queue.snapshots()[0]
    assert snapshot.first_service_tick == 10
    assert snapshot.remaining_bits == 60
    ledger = queue.ledger()
    assert ledger.terminal_payload_bits == 100
    assert ledger.service_consumed_bits == 40


def test_censor_and_phy_failure_are_distinct_terminal_causes() -> None:
    queue = _queue()
    first = _packet(0)
    second = _packet(1)
    queue.apply(EnqueuePacket(0, first))
    queue.apply(EnqueuePacket(0, second))
    failed = queue.apply(FailPacket(5, first.id))
    censored = queue.apply(CensorQueue(10))

    assert not isinstance(failed, ServiceResult)
    assert failed[0].terminal_cause is TerminalCause.PHY_FAILURE
    assert not isinstance(censored, ServiceResult)
    assert censored[0].terminal_cause is TerminalCause.CENSORED_AT_STOP
    assert queue.ledger().active_packets == 0


def test_same_tick_packets_are_never_overwritten() -> None:
    queue = _queue()
    packets = [_packet(index) for index in range(3)]
    for packet in packets:
        queue.apply(EnqueuePacket(0, packet))
    assert [snapshot.packet.id for snapshot in queue.snapshots()] == [
        packet.id for packet in packets
    ]


def test_queue_rejects_duplicate_unknown_and_nonmonotonic_commands() -> None:
    queue = _queue()
    packet = _packet(0)
    queue.apply(EnqueuePacket(10, _packet(0, arrival=10)))
    with pytest.raises(InvariantViolation, match="already exists"):
        queue.apply(EnqueuePacket(10, _packet(0, arrival=10)))
    with pytest.raises(InvariantViolation, match="unknown"):
        queue.apply(ExpirePacket(10, PacketId("packet/missing")))
    with pytest.raises(InvariantViolation, match="non-monotonic"):
        queue.apply(ApplyService(9, 1))
    assert packet.arrival_tick == 0


@pytest.mark.parametrize(
    ("max_packets", "max_bits"),
    [(None, None), (0, 100), (1, 0)],
)
def test_queue_capacity_configuration_fails_closed(
    max_packets: int | None,
    max_bits: int | None,
) -> None:
    with pytest.raises(InvariantViolation):
        _queue(max_packets=max_packets, max_bits=max_bits)


def test_packet_record_rejects_invalid_time_payload_and_deadline() -> None:
    with pytest.raises(InvariantViolation):
        _packet(0, arrival=-1)
    with pytest.raises(InvariantViolation):
        _packet(0, payload=0)
    with pytest.raises(InvariantViolation):
        _packet(0, arrival=5, deadline=5)


def test_reserved_service_excludes_packets_arriving_during_the_slot() -> None:
    queue = _queue()
    first = _packet(0, payload=100)
    later = _packet(1, arrival=5, payload=100)
    queue.apply(EnqueuePacket(0, first))
    reservation = queue.reserve_service(start_tick=0, completion_tick=10, capacity_bits=150)
    queue.apply(EnqueuePacket(5, later))

    result = queue.complete_reserved_service(reservation)

    assert result.consumed_bits == 100
    assert result.unused_bits == 50
    snapshots = queue.snapshots()
    assert snapshots[0].first_service_tick == 0
    assert snapshots[0].completion_tick == 10
    assert snapshots[1].first_service_tick is None
    assert snapshots[1].remaining_bits == 100


def test_reservation_expiring_before_completion_is_wasted_not_shifted() -> None:
    queue = _queue()
    first = _packet(0, payload=100, deadline=5)
    second = _packet(1, payload=100)
    queue.apply(EnqueuePacket(0, first))
    queue.apply(EnqueuePacket(0, second))
    reservation = queue.reserve_service(start_tick=0, completion_tick=10, capacity_bits=100)
    queue.apply(ExpirePacket(5, first.id))

    result = queue.complete_reserved_service(reservation)

    assert result.consumed_bits == 0
    assert result.unused_bits == 100
    assert queue.snapshots()[1].remaining_bits == 100
    assert queue.ledger().service_consumed_bits == 0


def test_reserved_service_completes_at_exact_deadline_before_expiration() -> None:
    queue = _queue()
    packet = _packet(0, payload=100, deadline=10)
    queue.apply(EnqueuePacket(0, packet))
    reservation = queue.reserve_service(start_tick=0, completion_tick=10, capacity_bits=100)
    completed = queue.complete_reserved_service(reservation)
    expired = queue.apply(ExpirePacket(10, packet.id))
    assert completed.consumed_bits == 100
    assert expired == ()
    assert queue.snapshots()[0].terminal_cause is TerminalCause.COMPLETED


def test_service_reservation_identity_and_time_contract_fail_closed() -> None:
    queue = _queue()
    queue.apply(EnqueuePacket(0, _packet(0)))
    with pytest.raises(InvariantViolation, match="complete after"):
        queue.reserve_service(start_tick=0, completion_tick=0, capacity_bits=1)
    with pytest.raises(InvariantViolation, match="negative"):
        queue.reserve_service(start_tick=0, completion_tick=1, capacity_bits=-1)
    reservation = queue.reserve_service(start_tick=0, completion_tick=1, capacity_bits=1)
    queue.complete_reserved_service(reservation)
    with pytest.raises(InvariantViolation, match="already completed"):
        queue.complete_reserved_service(reservation)
