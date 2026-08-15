"""Deterministic, visualization-ready full-allocation capacity diagnostic."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from nr_ran_sim.config.normalize import NormalizedScenario
from nr_ran_sim.errors import ArtifactError
from nr_ran_sim.radio.capacity import CapacityResult, evaluate_capacity
from nr_ran_sim.radio.resources import ResourceGrid, build_resource_grid
from nr_ran_sim.radio.snapshot import build_radio_snapshot, canonicalize_floats

CAPACITY_SNAPSHOT_SCHEMA_VERSION = "1.0"
FULL_ALLOCATION_CONTEXT = "independent-full-cell-allocation-diagnostic-v1"


@dataclass(frozen=True, slots=True)
class CapacityObservation:
    ue_id: str
    serving_cell_id: str
    sinr_db: float
    allocation_context: str
    capacity: CapacityResult

    def as_dict(self) -> dict[str, object]:
        return {
            "ue_id": self.ue_id,
            "serving_cell_id": self.serving_cell_id,
            "sinr_db": self.sinr_db,
            "allocation_context": self.allocation_context,
            "capacity": self.capacity.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class CapacitySnapshot:
    schema_version: str
    semantic_sha256: str
    radio_snapshot_sha256: str
    configuration_sha256: str
    master_seed: str
    replication_id: int
    scenario_id: str
    interpretation: str
    model_profiles: dict[str, str]
    resource_grid: ResourceGrid
    observations: tuple[CapacityObservation, ...]

    def as_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "radio_snapshot_sha256": self.radio_snapshot_sha256,
            "configuration_sha256": self.configuration_sha256,
            "master_seed": self.master_seed,
            "replication_id": self.replication_id,
            "scenario_id": self.scenario_id,
            "interpretation": self.interpretation,
            "model_profiles": dict(sorted(self.model_profiles.items())),
            "resource_grid": self.resource_grid.as_dict(),
            "observations": [observation.as_dict() for observation in self.observations],
        }
        if include_digest:
            payload["semantic_sha256"] = self.semantic_sha256
        return payload

    def to_json(self) -> str:
        return (
            json.dumps(
                canonicalize_floats(self.as_dict()),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )

    def write(self, path: Path, *, force: bool = False) -> None:
        if path.exists() and not force:
            raise ArtifactError(
                "output capacity snapshot already exists; pass --force to replace it",
                {"path": str(path)},
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_text(self.to_json(), encoding="utf-8", newline="\n")
            temporary.replace(path)
        except OSError as exc:
            raise ArtifactError(
                "unable to commit capacity snapshot",
                {"path": str(path), "detail": str(exc)},
            ) from exc
        finally:
            if temporary.exists():
                temporary.unlink()


def build_capacity_snapshot(
    scenario: NormalizedScenario,
    *,
    master_seed: str,
    replication_id: int,
) -> CapacitySnapshot:
    """Evaluate every UE independently against a full-cell PRB allocation."""

    radio_snapshot = build_radio_snapshot(
        scenario,
        master_seed=master_seed,
        replication_id=replication_id,
    )
    grid = build_resource_grid(scenario.radio)
    observations = tuple(
        CapacityObservation(
            ue_id=association.ue_id,
            serving_cell_id=association.serving_cell_id,
            sinr_db=association.sinr.sinr_db,
            allocation_context=FULL_ALLOCATION_CONTEXT,
            capacity=evaluate_capacity(
                scenario.radio,
                sinr_db=association.sinr.sinr_db,
                allocated_prbs=grid.prb_count,
            ),
        )
        for association in radio_snapshot.associations
    )
    snapshot = CapacitySnapshot(
        schema_version=CAPACITY_SNAPSHOT_SCHEMA_VERSION,
        semantic_sha256="",
        radio_snapshot_sha256=radio_snapshot.semantic_sha256,
        configuration_sha256=radio_snapshot.configuration_sha256,
        master_seed=radio_snapshot.master_seed,
        replication_id=radio_snapshot.replication_id,
        scenario_id=radio_snapshot.scenario_id,
        interpretation=(
            "Each UE is evaluated independently with every cell PRB; rates are not simultaneous, "
            "summable, scheduled, or measured throughput."
        ),
        model_profiles={
            **radio_snapshot.model_profiles,
            "link_adaptation": scenario.models.link_adaptation,
            "capacity": "single-layer-static-tbs-capacity-v1",
        },
        resource_grid=grid,
        observations=observations,
    )
    digest = hashlib.sha256(_semantic_bytes(snapshot)).hexdigest()
    return CapacitySnapshot(
        schema_version=snapshot.schema_version,
        semantic_sha256=digest,
        radio_snapshot_sha256=snapshot.radio_snapshot_sha256,
        configuration_sha256=snapshot.configuration_sha256,
        master_seed=snapshot.master_seed,
        replication_id=snapshot.replication_id,
        scenario_id=snapshot.scenario_id,
        interpretation=snapshot.interpretation,
        model_profiles=snapshot.model_profiles,
        resource_grid=snapshot.resource_grid,
        observations=snapshot.observations,
    )


def _semantic_bytes(snapshot: CapacitySnapshot) -> bytes:
    return json.dumps(
        canonicalize_floats(snapshot.as_dict(include_digest=False)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
