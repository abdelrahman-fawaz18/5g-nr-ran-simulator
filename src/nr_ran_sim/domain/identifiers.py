"""Stable, run-local identifiers used for trace correlation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from nr_ran_sim.errors import InvariantViolation

IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,254}$")


@dataclass(frozen=True, slots=True, order=True)
class StableId:
    """Validated value object; concrete subclasses prevent cross-entity ID mixing."""

    value: str
    kind: ClassVar[str] = "stable"

    def __post_init__(self) -> None:
        if not IDENTIFIER_PATTERN.fullmatch(self.value):
            raise InvariantViolation(
                "stable identifier contains unsupported characters or length",
                {"kind": self.kind, "value": self.value, "requirement": "SYS-007"},
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class CellId(StableId):
    kind: ClassVar[str] = "cell"


@dataclass(frozen=True, slots=True, order=True)
class UeId(StableId):
    kind: ClassVar[str] = "ue"


@dataclass(frozen=True, slots=True, order=True)
class BearerId(StableId):
    kind: ClassVar[str] = "bearer"


@dataclass(frozen=True, slots=True, order=True)
class PacketId(StableId):
    kind: ClassVar[str] = "packet"


@dataclass(frozen=True, slots=True, order=True)
class EventId(StableId):
    kind: ClassVar[str] = "event"


@dataclass(frozen=True, slots=True, order=True)
class RunId(StableId):
    kind: ClassVar[str] = "run"
