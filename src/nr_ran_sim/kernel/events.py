"""Typed kernel events and the frozen same-tick phase contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import TypeAlias

from nr_ran_sim.domain.identifiers import EventId
from nr_ran_sim.errors import InvariantViolation

TraceValue: TypeAlias = str | int | bool | tuple[str, ...] | tuple[int, ...] | None
EventOrderKey: TypeAlias = tuple[int, int, str, int]


class EventPhase(IntEnum):
    PRIOR_SERVICE_COMPLETION = 10
    DEADLINE_EXPIRATION = 20
    TOPOLOGY_CONTROL = 30
    PACKET_ARRIVAL = 40
    LINK_ASSOCIATION = 50
    SCHEDULING = 60
    SERVICE_RESERVATION = 70
    OBSERVATION = 80


class EventKind(StrEnum):
    SERVICE_COMPLETION = "service_completion"
    PACKET_DEADLINE = "packet_deadline"
    TOPOLOGY_CONTROL = "topology_control"
    PACKET_ARRIVAL = "packet_arrival"
    LINK_ASSOCIATION = "link_association"
    SCHEDULING = "scheduling"
    SERVICE_RESERVATION = "service_reservation"
    CENSOR_AT_STOP = "censor_at_stop"
    OBSERVATION = "observation"


@dataclass(frozen=True, slots=True)
class ScheduledEvent:
    id: EventId
    tick: int
    phase: EventPhase
    entity_key: str
    local_sequence: int
    kind: EventKind
    payload: object = None

    def __post_init__(self) -> None:
        if self.tick < 0 or self.local_sequence < 0 or not self.entity_key:
            raise InvariantViolation(
                "scheduled event has an invalid ordering field",
                {
                    "event_id": str(self.id),
                    "tick": self.tick,
                    "entity_key": self.entity_key,
                    "local_sequence": self.local_sequence,
                    "requirement": "TIME-004",
                },
            )

    @property
    def order_key(self) -> EventOrderKey:
        return (self.tick, int(self.phase), self.entity_key, self.local_sequence)


@dataclass(frozen=True, slots=True)
class EventResult:
    outcome: str
    details: tuple[tuple[str, TraceValue], ...] = ()
    followups: tuple[ScheduledEvent, ...] = ()

    @classmethod
    def create(
        cls,
        outcome: str,
        *,
        details: dict[str, TraceValue] | None = None,
        followups: tuple[ScheduledEvent, ...] = (),
    ) -> EventResult:
        return cls(
            outcome=outcome,
            details=tuple(sorted((details or {}).items())),
            followups=followups,
        )


@dataclass(frozen=True, slots=True)
class SemanticEvent:
    event_id: str
    tick: int
    phase: int
    phase_name: str
    entity_key: str
    local_sequence: int
    kind: str
    outcome: str
    details: tuple[tuple[str, TraceValue], ...]

    @classmethod
    def from_result(cls, event: ScheduledEvent, result: EventResult) -> SemanticEvent:
        return cls(
            event_id=str(event.id),
            tick=event.tick,
            phase=int(event.phase),
            phase_name=event.phase.name.lower(),
            entity_key=event.entity_key,
            local_sequence=event.local_sequence,
            kind=event.kind.value,
            outcome=result.outcome,
            details=result.details,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "details": dict(self.details),
            "entity_key": self.entity_key,
            "event_id": self.event_id,
            "kind": self.kind,
            "local_sequence": self.local_sequence,
            "outcome": self.outcome,
            "phase": self.phase,
            "phase_name": self.phase_name,
            "tick": self.tick,
        }


def create_scheduled_event(
    *,
    tick: int,
    phase: EventPhase,
    entity_key: str,
    local_sequence: int,
    kind: EventKind,
    payload: object = None,
) -> ScheduledEvent:
    """Create a content-derived event ID independent of insertion order."""

    identity = f"{tick}|{int(phase)}|{entity_key}|{local_sequence}|{kind.value}".encode()
    fingerprint = hashlib.sha256(identity).hexdigest()
    return ScheduledEvent(
        id=EventId(f"event/{tick:019d}/{int(phase):02d}/{fingerprint}"),
        tick=tick,
        phase=phase,
        entity_key=entity_key,
        local_sequence=local_sequence,
        kind=kind,
        payload=payload,
    )
