"""Immutable entity records and deterministic scenario expansion."""

from __future__ import annotations

from dataclasses import dataclass

from nr_ran_sim.config.normalize import NormalizedScenario
from nr_ran_sim.domain.identifiers import BearerId, CellId, UeId
from nr_ran_sim.errors import InvariantViolation


@dataclass(frozen=True, slots=True)
class CellRecord:
    id: CellId
    configuration_id: str


@dataclass(frozen=True, slots=True)
class UeRecord:
    id: UeId
    group_id: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class BearerRecord:
    id: BearerId
    ue_id: UeId
    traffic_profile_id: str


@dataclass(frozen=True, slots=True)
class EntityRegistry:
    cells: tuple[CellRecord, ...]
    ues: tuple[UeRecord, ...]
    bearers: tuple[BearerRecord, ...]

    def bearer(self, bearer_id: BearerId) -> BearerRecord:
        for bearer in self.bearers:
            if bearer.id == bearer_id:
                return bearer
        raise InvariantViolation(
            "bearer identifier is not present in the entity registry",
            {"bearer_id": str(bearer_id), "requirement": "SYS-007"},
        )


def build_entity_registry(scenario: NormalizedScenario) -> EntityRegistry:
    """Expand configuration groups in lexical/ordinal order, never mapping insertion order."""

    cells = tuple(
        CellRecord(id=CellId(f"cell/{cell_id}"), configuration_id=cell_id)
        for cell_id in sorted(scenario.topology.cells)
    )
    ues: list[UeRecord] = []
    bearers: list[BearerRecord] = []
    for group_id in sorted(scenario.topology.ue_groups):
        group = scenario.topology.ue_groups[group_id]
        for ordinal in range(group.count):
            ue_id = UeId(f"ue/{group_id}/{ordinal:06d}")
            ues.append(UeRecord(id=ue_id, group_id=group_id, ordinal=ordinal))
            for profile_id in sorted(group.bearers):
                bearer_id = BearerId(f"bearer/{group_id}/{ordinal:06d}/{profile_id}")
                bearers.append(
                    BearerRecord(
                        id=bearer_id,
                        ue_id=ue_id,
                        traffic_profile_id=profile_id,
                    )
                )
    return EntityRegistry(cells=cells, ues=tuple(ues), bearers=tuple(bearers))
