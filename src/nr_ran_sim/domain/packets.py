"""Immutable packet records and lifecycle observations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from nr_ran_sim.domain.identifiers import BearerId, EventId, PacketId
from nr_ran_sim.errors import InvariantViolation


class PacketCohort(StrEnum):
    WARMUP = "warmup"
    MEASUREMENT = "measurement"


class TerminalCause(StrEnum):
    COMPLETED = "completed"
    OVERFLOW_DROP = "overflow_drop"
    DEADLINE_EXPIRED = "deadline_expired"
    PHY_FAILURE = "phy_failure"
    CENSORED_AT_STOP = "censored_at_stop"


class PacketEventKind(StrEnum):
    ARRIVED = "arrived"
    PARTIAL_SERVICE = "partial_service"
    COMPLETED = "completed"
    OVERFLOW_DROPPED = "overflow_dropped"
    DEADLINE_EXPIRED = "deadline_expired"
    PHY_FAILED = "phy_failed"
    CENSORED = "censored"


@dataclass(frozen=True, slots=True)
class PacketRecord:
    id: PacketId
    bearer_id: BearerId
    arrival_tick: int
    payload_bits: int
    deadline_tick: int | None
    cohort: PacketCohort

    def __post_init__(self) -> None:
        if self.arrival_tick < 0 or self.payload_bits <= 0:
            raise InvariantViolation(
                "packet arrival tick and payload are outside the mechanics domain",
                {
                    "packet_id": str(self.id),
                    "arrival_tick": self.arrival_tick,
                    "payload_bits": self.payload_bits,
                    "requirement": "QOS-002",
                },
            )
        if self.deadline_tick is not None and self.deadline_tick <= self.arrival_tick:
            raise InvariantViolation(
                "packet deadline must be later than its arrival",
                {
                    "packet_id": str(self.id),
                    "arrival_tick": self.arrival_tick,
                    "deadline_tick": self.deadline_tick,
                    "requirement": "QOS-002",
                },
            )


@dataclass(frozen=True, slots=True)
class PacketSnapshot:
    packet: PacketRecord
    remaining_bits: int
    first_service_tick: int | None
    completion_tick: int | None
    terminal_tick: int | None
    terminal_cause: TerminalCause | None


@dataclass(frozen=True, slots=True)
class PacketLifecycleEvent:
    id: EventId
    packet_id: PacketId
    bearer_id: BearerId
    tick: int
    kind: PacketEventKind
    affected_bits: int
    remaining_bits: int
    terminal_cause: TerminalCause | None = None
