"""Canonical semantic traces and deterministic replay digests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from nr_ran_sim.kernel.events import SemanticEvent


@dataclass(frozen=True, slots=True)
class SemanticTrace:
    events: tuple[SemanticEvent, ...]
    schema_version: str = "1.0"

    def as_dict(self) -> dict[str, object]:
        return {
            "events": [event.as_dict() for event in self.events],
            "trace_schema_version": self.schema_version,
        }

    def to_json(self) -> str:
        return (
            json.dumps(
                self.as_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()
