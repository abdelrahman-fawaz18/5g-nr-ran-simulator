"""Per-bearer FIFO packet queue with exact lifecycle and bit accounting."""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass

from nr_ran_sim.domain.entities import BearerRecord
from nr_ran_sim.domain.identifiers import BearerId, EventId, PacketId
from nr_ran_sim.domain.packets import (
    PacketEventKind,
    PacketLifecycleEvent,
    PacketRecord,
    PacketSnapshot,
    TerminalCause,
)
from nr_ran_sim.errors import InvariantViolation
from nr_ran_sim.traffic.commands import (
    ApplyService,
    CensorQueue,
    EnqueuePacket,
    ExpirePacket,
    FailPacket,
    QueueCommand,
)


@dataclass(slots=True)
class _PacketState:
    packet: PacketRecord
    remaining_bits: int
    first_service_tick: int | None = None
    completion_tick: int | None = None
    terminal_tick: int | None = None
    terminal_cause: TerminalCause | None = None

    def snapshot(self) -> PacketSnapshot:
        return PacketSnapshot(
            packet=self.packet,
            remaining_bits=self.remaining_bits,
            first_service_tick=self.first_service_tick,
            completion_tick=self.completion_tick,
            terminal_tick=self.terminal_tick,
            terminal_cause=self.terminal_cause,
        )


@dataclass(frozen=True, slots=True)
class ServiceResult:
    requested_bits: int
    consumed_bits: int
    unused_bits: int
    events: tuple[PacketLifecycleEvent, ...]


@dataclass(frozen=True, slots=True)
class ReservedPacketService:
    """Payload reserved from one packet at the start of a service interval."""

    packet_id: PacketId
    reserved_bits: int


@dataclass(frozen=True, slots=True)
class ServiceReservation:
    """Immutable FIFO service plan committed for one future completion tick."""

    id: str
    bearer_id: BearerId
    start_tick: int
    completion_tick: int
    capacity_bits: int
    reserved_bits: int
    unreserved_bits: int
    packets: tuple[ReservedPacketService, ...]


@dataclass(frozen=True, slots=True)
class QueueLedger:
    offered_packets: int
    offered_bits: int
    active_packets: int
    queued_remaining_bits: int
    active_served_bits: int
    completed_packets: int
    completed_payload_bits: int
    terminal_packets: int
    terminal_payload_bits: int
    service_consumed_bits: int

    def assert_conserved(self) -> None:
        accounted = (
            self.queued_remaining_bits
            + self.active_served_bits
            + self.completed_payload_bits
            + self.terminal_payload_bits
        )
        if accounted != self.offered_bits:
            raise InvariantViolation(
                "packet/bit conservation ledger does not reconcile",
                {
                    "offered_bits": self.offered_bits,
                    "accounted_bits": accounted,
                    "requirement": "QOS-002",
                },
            )
        if self.offered_packets != (
            self.active_packets + self.completed_packets + self.terminal_packets
        ):
            raise InvariantViolation(
                "packet-count conservation ledger does not reconcile",
                {
                    "offered_packets": self.offered_packets,
                    "active_packets": self.active_packets,
                    "completed_packets": self.completed_packets,
                    "terminal_packets": self.terminal_packets,
                    "requirement": "QOS-001",
                },
            )


class BearerQueue:
    """Own mutable packet state for exactly one bearer."""

    def __init__(
        self,
        bearer: BearerRecord,
        *,
        max_packets: int | None,
        max_payload_bits: int | None,
    ) -> None:
        if max_packets is None and max_payload_bits is None:
            raise InvariantViolation(
                "bearer queue must have at least one finite capacity bound",
                {"bearer_id": str(bearer.id), "requirement": "QOS-006"},
            )
        if (max_packets is not None and max_packets <= 0) or (
            max_payload_bits is not None and max_payload_bits <= 0
        ):
            raise InvariantViolation(
                "bearer queue capacity bounds must be strictly positive",
                {"bearer_id": str(bearer.id), "requirement": "QOS-006"},
            )
        self.bearer = bearer
        self.max_packets = max_packets
        self.max_payload_bits = max_payload_bits
        self._active: deque[PacketId] = deque()
        self._states: dict[PacketId, _PacketState] = {}
        self._last_tick = 0
        self._transition_sequence = 0
        self._service_consumed_bits = 0
        self._queued_payload_bits = 0
        self._known_reservation_ids: set[str] = set()
        self._completed_reservation_ids: set[str] = set()

    def apply(self, command: QueueCommand) -> tuple[PacketLifecycleEvent, ...] | ServiceResult:
        self._check_tick(command.tick)
        if isinstance(command, EnqueuePacket):
            return self._enqueue(command)
        if isinstance(command, ApplyService):
            return self._service(command)
        if isinstance(command, ExpirePacket):
            event = self._terminate_packet(
                command.packet_id,
                command.tick,
                TerminalCause.DEADLINE_EXPIRED,
                PacketEventKind.DEADLINE_EXPIRED,
                require_deadline=True,
            )
            return () if event is None else (event,)
        if isinstance(command, FailPacket):
            event = self._terminate_packet(
                command.packet_id,
                command.tick,
                TerminalCause.PHY_FAILURE,
                PacketEventKind.PHY_FAILED,
            )
            return () if event is None else (event,)
        return self._censor(command)

    def snapshots(self) -> tuple[PacketSnapshot, ...]:
        return tuple(self._states[packet_id].snapshot() for packet_id in sorted(self._states))

    def ledger(self) -> QueueLedger:
        active_states = [self._states[packet_id] for packet_id in self._active]
        completed = [
            state
            for state in self._states.values()
            if state.terminal_cause is TerminalCause.COMPLETED
        ]
        other_terminal = [
            state
            for state in self._states.values()
            if state.terminal_cause is not None
            and state.terminal_cause is not TerminalCause.COMPLETED
        ]
        queued_remaining_bits = sum(state.remaining_bits for state in active_states)
        if queued_remaining_bits != self._queued_payload_bits:
            raise InvariantViolation(
                "cached queue occupancy does not match packet state",
                {
                    "bearer_id": str(self.bearer.id),
                    "cached_bits": self._queued_payload_bits,
                    "packet_state_bits": queued_remaining_bits,
                    "requirement": "QOS-002",
                },
            )
        ledger = QueueLedger(
            offered_packets=len(self._states),
            offered_bits=sum(state.packet.payload_bits for state in self._states.values()),
            active_packets=len(active_states),
            queued_remaining_bits=queued_remaining_bits,
            active_served_bits=sum(
                state.packet.payload_bits - state.remaining_bits for state in active_states
            ),
            completed_packets=len(completed),
            completed_payload_bits=sum(state.packet.payload_bits for state in completed),
            terminal_packets=len(other_terminal),
            terminal_payload_bits=sum(state.packet.payload_bits for state in other_terminal),
            service_consumed_bits=self._service_consumed_bits,
        )
        ledger.assert_conserved()
        return ledger

    @property
    def queued_packet_count(self) -> int:
        return len(self._active)

    @property
    def queued_payload_bits(self) -> int:
        return self._queued_payload_bits

    def reserve_service(
        self,
        *,
        start_tick: int,
        completion_tick: int,
        capacity_bits: int,
    ) -> ServiceReservation:
        """Reserve only payload visible at ``start_tick`` for later slot completion.

        Reservation records the first-service tick without removing queue payload. Arrivals after
        the scheduling boundary therefore cannot consume capacity committed for the prior slot.
        """

        self._check_tick(start_tick)
        if completion_tick <= start_tick:
            raise InvariantViolation(
                "service reservation must complete after it starts",
                {
                    "start_tick": start_tick,
                    "completion_tick": completion_tick,
                    "requirement": "TIME-002",
                },
            )
        if capacity_bits < 0:
            raise InvariantViolation(
                "service reservation capacity cannot be negative",
                {"capacity_bits": capacity_bits, "requirement": "MAC-009"},
            )
        available = capacity_bits
        packet_services: list[ReservedPacketService] = []
        for packet_id in self._active:
            if available == 0:
                break
            state = self._states[packet_id]
            reserved = min(available, state.remaining_bits)
            if reserved == 0:
                continue
            if state.first_service_tick is None:
                state.first_service_tick = start_tick
            packet_services.append(
                ReservedPacketService(packet_id=packet_id, reserved_bits=reserved)
            )
            available -= reserved
        reserved_bits = capacity_bits - available
        identity = "|".join(
            (
                str(self.bearer.id),
                str(start_tick),
                str(completion_tick),
                str(capacity_bits),
                *(f"{item.packet_id}:{item.reserved_bits}" for item in packet_services),
            )
        )
        reservation_id = f"service-reservation/{hashlib.sha256(identity.encode()).hexdigest()}"
        if reservation_id in self._known_reservation_ids:
            raise InvariantViolation(
                "duplicate service reservation identity",
                {"reservation_id": reservation_id, "requirement": "SYS-007"},
            )
        self._known_reservation_ids.add(reservation_id)
        return ServiceReservation(
            id=reservation_id,
            bearer_id=self.bearer.id,
            start_tick=start_tick,
            completion_tick=completion_tick,
            capacity_bits=capacity_bits,
            reserved_bits=reserved_bits,
            unreserved_bits=available,
            packets=tuple(packet_services),
        )

    def complete_reserved_service(self, reservation: ServiceReservation) -> ServiceResult:
        """Realize exactly the packet payload selected at the scheduling boundary."""

        self._check_tick(reservation.completion_tick)
        if reservation.bearer_id != self.bearer.id:
            raise InvariantViolation(
                "service reservation belongs to another bearer",
                {
                    "reservation_id": reservation.id,
                    "bearer_id": str(self.bearer.id),
                    "reservation_bearer_id": str(reservation.bearer_id),
                    "requirement": "MAC-009",
                },
            )
        if reservation.id not in self._known_reservation_ids:
            raise InvariantViolation(
                "service reservation is unknown to this bearer queue",
                {"reservation_id": reservation.id, "requirement": "MAC-009"},
            )
        if reservation.id in self._completed_reservation_ids:
            raise InvariantViolation(
                "service reservation has already completed",
                {"reservation_id": reservation.id, "requirement": "MAC-009"},
            )
        events: list[PacketLifecycleEvent] = []
        consumed = 0
        for item in reservation.packets:
            state = self._states.get(item.packet_id)
            if state is None:
                raise InvariantViolation(
                    "service reservation references an unknown packet",
                    {
                        "reservation_id": reservation.id,
                        "packet_id": str(item.packet_id),
                        "requirement": "QOS-002",
                    },
                )
            if state.terminal_cause is not None:
                continue
            if item.packet_id not in self._active or item.reserved_bits > state.remaining_bits:
                raise InvariantViolation(
                    "reserved packet state changed outside the service contract",
                    {
                        "reservation_id": reservation.id,
                        "packet_id": str(item.packet_id),
                        "reserved_bits": item.reserved_bits,
                        "remaining_bits": state.remaining_bits,
                        "requirement": "MAC-009",
                    },
                )
            state.remaining_bits -= item.reserved_bits
            self._queued_payload_bits -= item.reserved_bits
            self._service_consumed_bits += item.reserved_bits
            consumed += item.reserved_bits
            if state.remaining_bits:
                events.append(
                    self._event(
                        state,
                        reservation.completion_tick,
                        PacketEventKind.PARTIAL_SERVICE,
                        item.reserved_bits,
                    )
                )
                continue
            self._active.remove(item.packet_id)
            state.completion_tick = reservation.completion_tick
            state.terminal_tick = reservation.completion_tick
            state.terminal_cause = TerminalCause.COMPLETED
            events.append(
                self._event(
                    state,
                    reservation.completion_tick,
                    PacketEventKind.COMPLETED,
                    item.reserved_bits,
                    TerminalCause.COMPLETED,
                )
            )
        self._completed_reservation_ids.add(reservation.id)
        return ServiceResult(
            requested_bits=reservation.capacity_bits,
            consumed_bits=consumed,
            unused_bits=reservation.capacity_bits - consumed,
            events=tuple(events),
        )

    def _enqueue(self, command: EnqueuePacket) -> tuple[PacketLifecycleEvent, ...]:
        packet = command.packet
        if packet.bearer_id != self.bearer.id or packet.arrival_tick != command.tick:
            raise InvariantViolation(
                "packet arrival command does not match its bearer or timestamp",
                {
                    "packet_id": str(packet.id),
                    "bearer_id": str(self.bearer.id),
                    "command_tick": command.tick,
                    "requirement": "QOS-001",
                },
            )
        if packet.id in self._states:
            raise InvariantViolation(
                "packet identifier already exists in the bearer lifecycle",
                {"packet_id": str(packet.id), "requirement": "QOS-003"},
            )
        state = _PacketState(packet=packet, remaining_bits=packet.payload_bits)
        self._states[packet.id] = state
        events = [self._event(state, command.tick, PacketEventKind.ARRIVED, packet.payload_bits)]
        packet_limit_exceeded = (
            self.max_packets is not None and len(self._active) + 1 > self.max_packets
        )
        bit_limit_exceeded = (
            self.max_payload_bits is not None
            and self.queued_payload_bits + packet.payload_bits > self.max_payload_bits
        )
        if packet_limit_exceeded or bit_limit_exceeded:
            state.terminal_tick = command.tick
            state.terminal_cause = TerminalCause.OVERFLOW_DROP
            events.append(
                self._event(
                    state,
                    command.tick,
                    PacketEventKind.OVERFLOW_DROPPED,
                    packet.payload_bits,
                    TerminalCause.OVERFLOW_DROP,
                )
            )
            return tuple(events)
        self._active.append(packet.id)
        self._queued_payload_bits += packet.payload_bits
        return tuple(events)

    def _service(self, command: ApplyService) -> ServiceResult:
        if command.capacity_bits < 0:
            raise InvariantViolation(
                "service capacity cannot be negative",
                {"capacity_bits": command.capacity_bits, "requirement": "MAC-009"},
            )
        available = command.capacity_bits
        events: list[PacketLifecycleEvent] = []
        while available and self._active:
            packet_id = self._active[0]
            state = self._states[packet_id]
            deadline = state.packet.deadline_tick
            if deadline is not None and deadline < command.tick:
                raise InvariantViolation(
                    "overdue packet reached service before its deadline event",
                    {
                        "packet_id": str(packet_id),
                        "deadline_tick": deadline,
                        "service_tick": command.tick,
                        "requirement": "TIME-005",
                    },
                )
            consumed = min(available, state.remaining_bits)
            if state.first_service_tick is None:
                state.first_service_tick = command.tick
            state.remaining_bits -= consumed
            self._queued_payload_bits -= consumed
            available -= consumed
            self._service_consumed_bits += consumed
            if state.remaining_bits:
                events.append(
                    self._event(
                        state,
                        command.tick,
                        PacketEventKind.PARTIAL_SERVICE,
                        consumed,
                    )
                )
                continue
            self._active.popleft()
            state.completion_tick = command.tick
            state.terminal_tick = command.tick
            state.terminal_cause = TerminalCause.COMPLETED
            events.append(
                self._event(
                    state,
                    command.tick,
                    PacketEventKind.COMPLETED,
                    consumed,
                    TerminalCause.COMPLETED,
                )
            )
        return ServiceResult(
            requested_bits=command.capacity_bits,
            consumed_bits=command.capacity_bits - available,
            unused_bits=available,
            events=tuple(events),
        )

    def _terminate_packet(
        self,
        packet_id: PacketId,
        tick: int,
        cause: TerminalCause,
        kind: PacketEventKind,
        *,
        require_deadline: bool = False,
    ) -> PacketLifecycleEvent | None:
        state = self._states.get(packet_id)
        if state is None:
            raise InvariantViolation(
                "terminal command references an unknown packet",
                {"packet_id": str(packet_id), "requirement": "QOS-002"},
            )
        if state.terminal_cause is not None:
            return None
        if require_deadline:
            deadline = state.packet.deadline_tick
            if deadline is None or tick < deadline:
                raise InvariantViolation(
                    "deadline expiration occurred before the configured packet deadline",
                    {
                        "packet_id": str(packet_id),
                        "deadline_tick": deadline,
                        "event_tick": tick,
                        "requirement": "TIME-006",
                    },
                )
        self._active.remove(packet_id)
        self._queued_payload_bits -= state.remaining_bits
        state.terminal_tick = tick
        state.terminal_cause = cause
        return self._event(state, tick, kind, state.remaining_bits, cause)

    def _censor(self, command: CensorQueue) -> tuple[PacketLifecycleEvent, ...]:
        events: list[PacketLifecycleEvent] = []
        for packet_id in tuple(self._active):
            event = self._terminate_packet(
                packet_id,
                command.tick,
                TerminalCause.CENSORED_AT_STOP,
                PacketEventKind.CENSORED,
            )
            if event is not None:
                events.append(event)
        return tuple(events)

    def _check_tick(self, tick: int) -> None:
        if tick < self._last_tick:
            raise InvariantViolation(
                "bearer queue command time is non-monotonic",
                {
                    "tick": tick,
                    "last_tick": self._last_tick,
                    "bearer_id": str(self.bearer.id),
                    "requirement": "TIME-009",
                },
            )
        self._last_tick = tick

    def _event(
        self,
        state: _PacketState,
        tick: int,
        kind: PacketEventKind,
        affected_bits: int,
        cause: TerminalCause | None = None,
    ) -> PacketLifecycleEvent:
        identity = (
            f"{self.bearer.id}|{self._transition_sequence}|{state.packet.id}|{tick}|{kind.value}"
        )
        digest = hashlib.sha256(identity.encode()).hexdigest()
        event = PacketLifecycleEvent(
            id=EventId(f"packet-event/{digest}"),
            packet_id=state.packet.id,
            bearer_id=self.bearer.id,
            tick=tick,
            kind=kind,
            affected_bits=affected_bits,
            remaining_bits=state.remaining_bits,
            terminal_cause=cause,
        )
        self._transition_sequence += 1
        return event
