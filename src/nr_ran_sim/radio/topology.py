"""Immutable explicit/seeded topology construction with bounded rejection sampling."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from nr_ran_sim.config.normalize import (
    NormalizedExplicitPlacement,
    NormalizedScenario,
)
from nr_ran_sim.domain.entities import build_entity_registry
from nr_ran_sim.errors import RunExecutionError
from nr_ran_sim.experiments.seeds import SemanticRngRegistry
from nr_ran_sim.radio.geometry import Position3D


@dataclass(frozen=True, slots=True)
class RadioCell:
    id: str
    configuration_id: str
    position: Position3D
    transmit_power_w: float
    transmit_power_dbm: float
    antenna_gain_dbi: float
    miscellaneous_loss_db: float

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "configuration_id": self.configuration_id,
            "position": self.position.as_dict(),
            "transmit_power_w": self.transmit_power_w,
            "transmit_power_dbm": self.transmit_power_dbm,
            "antenna_gain_dbi": self.antenna_gain_dbi,
            "miscellaneous_loss_db": self.miscellaneous_loss_db,
        }


@dataclass(frozen=True, slots=True)
class RadioUe:
    id: str
    group_id: str
    ordinal: int
    position: Position3D
    receiver_noise_figure_db: float
    antenna_gain_dbi: float
    penetration_loss_db: float
    placement_attempts: int

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "ordinal": self.ordinal,
            "position": self.position.as_dict(),
            "receiver_noise_figure_db": self.receiver_noise_figure_db,
            "antenna_gain_dbi": self.antenna_gain_dbi,
            "penetration_loss_db": self.penetration_loss_db,
            "placement_attempts": self.placement_attempts,
        }


@dataclass(frozen=True, slots=True)
class RadioTopology:
    coordinate_system: str
    cells: tuple[RadioCell, ...]
    ues: tuple[RadioUe, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "coordinate_system": self.coordinate_system,
            "cells": [cell.as_dict() for cell in self.cells],
            "ues": [ue.as_dict() for ue in self.ues],
        }


def build_radio_topology(
    scenario: NormalizedScenario,
    rng_registry: SemanticRngRegistry,
) -> RadioTopology:
    """Expand cells/UEs deterministically and enforce configured minimum distances."""

    entity_registry = build_entity_registry(scenario)
    cells = tuple(
        _radio_cell(str(cell.id), cell.configuration_id, scenario) for cell in entity_registry.cells
    )
    ues: list[RadioUe] = []
    for entity in entity_registry.ues:
        group = scenario.topology.ue_groups[entity.group_id]
        placement = group.placement
        if isinstance(placement, NormalizedExplicitPlacement):
            normalized_position = placement.positions[entity.ordinal]
            position = Position3D(
                float(normalized_position.x_m),
                float(normalized_position.y_m),
                float(normalized_position.z_m),
            )
            attempts = 0
        else:
            stream_path = f"topology/{entity.id}/position"
            rng = rng_registry.acquire(stream_path, owner=f"radio-topology:{entity.id}")
            position, attempts = _sample_position(
                rng.uniform,
                float(placement.x_min_m),
                float(placement.x_max_m),
                float(placement.y_min_m),
                float(placement.y_max_m),
                float(placement.height_m),
                float(placement.minimum_2d_distance_m),
                placement.attempt_budget,
                cells,
                str(entity.id),
            )
        ues.append(
            RadioUe(
                id=str(entity.id),
                group_id=entity.group_id,
                ordinal=entity.ordinal,
                position=position,
                receiver_noise_figure_db=float(group.receiver_noise_figure_db),
                antenna_gain_dbi=float(group.antenna_gain_dbi),
                penetration_loss_db=float(group.penetration_loss_db),
                placement_attempts=attempts,
            )
        )
    return RadioTopology(
        coordinate_system=scenario.topology.coordinate_system,
        cells=cells,
        ues=tuple(ues),
    )


def _radio_cell(cell_id: str, configuration_id: str, scenario: NormalizedScenario) -> RadioCell:
    config = scenario.topology.cells[configuration_id]
    return RadioCell(
        id=cell_id,
        configuration_id=configuration_id,
        position=Position3D(
            float(config.position.x_m),
            float(config.position.y_m),
            float(config.position.z_m),
        ),
        transmit_power_w=float(config.transmit_power_w),
        transmit_power_dbm=float(config.transmit_power_dbm),
        antenna_gain_dbi=float(config.antenna_gain_dbi),
        miscellaneous_loss_db=float(config.miscellaneous_loss_db),
    )


def _sample_position(
    uniform: Callable[[float, float], float],
    x_min_m: float,
    x_max_m: float,
    y_min_m: float,
    y_max_m: float,
    height_m: float,
    minimum_distance_m: float,
    attempt_budget: int,
    cells: tuple[RadioCell, ...],
    ue_id: str,
) -> tuple[Position3D, int]:
    for attempt in range(1, attempt_budget + 1):
        position = Position3D(
            uniform(x_min_m, x_max_m),
            uniform(y_min_m, y_max_m),
            height_m,
        )
        if all(
            _horizontal_distance(position, cell.position) >= minimum_distance_m for cell in cells
        ):
            return position, attempt
    raise RunExecutionError(
        "unable to place UE within the configured attempt budget",
        {
            "ue_id": ue_id,
            "attempt_budget": attempt_budget,
            "minimum_2d_distance_m": minimum_distance_m,
            "requirement": "PROP-011",
        },
    )


def _horizontal_distance(left: Position3D, right: Position3D) -> float:
    return math.hypot(left.x_m - right.x_m, left.y_m - right.y_m)
