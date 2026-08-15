"""Explicit-metre Cartesian geometry for outdoor BS-to-UE links."""

from __future__ import annotations

import math
from dataclasses import dataclass

from nr_ran_sim.errors import ModelDomainError


@dataclass(frozen=True, slots=True)
class Position3D:
    """A point in the scenario's declared local Cartesian system, in metres."""

    x_m: float
    y_m: float
    z_m: float

    def __post_init__(self) -> None:
        values = (self.x_m, self.y_m, self.z_m)
        if not all(math.isfinite(value) for value in values):
            raise ModelDomainError(
                "Cartesian coordinates must be finite",
                {"position_m": values, "requirement": "PROP-001"},
            )

    def as_dict(self) -> dict[str, float]:
        return {"x_m": self.x_m, "y_m": self.y_m, "z_m": self.z_m}


@dataclass(frozen=True, slots=True)
class LinkGeometry:
    """Auditable 2D/3D distance components for one transmitter-receiver pair."""

    transmitter: Position3D
    receiver: Position3D
    horizontal_distance_m: float
    direct_distance_m: float
    height_difference_m: float

    def as_dict(self) -> dict[str, object]:
        return {
            "transmitter": self.transmitter.as_dict(),
            "receiver": self.receiver.as_dict(),
            "horizontal_distance_m": self.horizontal_distance_m,
            "direct_distance_m": self.direct_distance_m,
            "height_difference_m": self.height_difference_m,
        }


def link_geometry(transmitter: Position3D, receiver: Position3D) -> LinkGeometry:
    """Return horizontal and direct distances without unit conversion or clipping."""

    delta_x = receiver.x_m - transmitter.x_m
    delta_y = receiver.y_m - transmitter.y_m
    delta_z = receiver.z_m - transmitter.z_m
    horizontal = math.hypot(delta_x, delta_y)
    direct = math.hypot(horizontal, delta_z)
    return LinkGeometry(
        transmitter=transmitter,
        receiver=receiver,
        horizontal_distance_m=horizontal,
        direct_distance_m=direct,
        height_difference_m=abs(delta_z),
    )
