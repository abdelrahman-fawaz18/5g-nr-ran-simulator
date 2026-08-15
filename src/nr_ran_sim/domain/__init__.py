"""Typed domain records for deterministic simulation mechanics."""

from nr_ran_sim.domain.entities import (
    BearerRecord,
    CellRecord,
    EntityRegistry,
    UeRecord,
    build_entity_registry,
)
from nr_ran_sim.domain.identifiers import BearerId, CellId, EventId, PacketId, RunId, UeId
from nr_ran_sim.domain.packets import (
    PacketCohort,
    PacketEventKind,
    PacketLifecycleEvent,
    PacketRecord,
    PacketSnapshot,
    TerminalCause,
)

__all__ = [
    "BearerId",
    "BearerRecord",
    "CellId",
    "CellRecord",
    "EntityRegistry",
    "EventId",
    "PacketCohort",
    "PacketEventKind",
    "PacketId",
    "PacketLifecycleEvent",
    "PacketRecord",
    "PacketSnapshot",
    "RunId",
    "TerminalCause",
    "UeId",
    "UeRecord",
    "build_entity_registry",
]
