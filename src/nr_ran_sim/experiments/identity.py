"""Content-derived run identity and separated diagnostic metadata."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from nr_ran_sim.config.manifest import canonical_json_bytes
from nr_ran_sim.config.normalize import NormalizedScenario
from nr_ran_sim.domain.identifiers import RunId
from nr_ran_sim.errors import ConfigurationValidationError
from nr_ran_sim.experiments.seeds import MASTER_SEED, RngStreamRecord
from nr_ran_sim.metadata import environment_metadata


@dataclass(frozen=True, slots=True)
class RunIdentity:
    id: RunId
    identity_schema_version: str
    configuration_sha256: str
    master_seed: str
    replication_id: int
    code_revision: str
    model_profiles: tuple[tuple[str, str], ...]
    experiment_factors: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "code_revision": self.code_revision,
            "configuration_sha256": self.configuration_sha256,
            "experiment_factors": dict(self.experiment_factors),
            "identity_schema_version": self.identity_schema_version,
            "master_seed": self.master_seed,
            "model_profiles": dict(self.model_profiles),
            "replication_id": self.replication_id,
            "run_id": str(self.id),
        }


@dataclass(frozen=True, slots=True)
class RunMetadata:
    identity: RunIdentity
    working_tree_dirty: bool
    rng_streams: tuple[RngStreamRecord, ...]
    environment: dict[str, Any]

    def as_dict(self) -> dict[str, object]:
        return {
            "environment": self.environment,
            "identity": self.identity.as_dict(),
            "rng_streams": [asdict(record) for record in self.rng_streams],
            "working_tree_dirty": self.working_tree_dirty,
        }


def build_run_identity(
    *,
    configuration_sha256: str,
    master_seed: str,
    replication_id: int,
    code_revision: str,
    model_profiles: dict[str, str],
    experiment_factors: dict[str, str] | None = None,
) -> RunIdentity:
    """Hash all scientific run dimensions named by EXP-006."""

    if not re.fullmatch(r"[0-9a-fA-F]{64}", configuration_sha256):
        raise ConfigurationValidationError(
            "configuration identity must be a 64-character SHA-256 hexadecimal digest",
            {"field": "configuration_sha256", "requirement": "EXP-006"},
        )
    if not MASTER_SEED.fullmatch(master_seed):
        raise ConfigurationValidationError(
            "master seed must be a 128-bit hexadecimal string prefixed by 0x",
            {"field": "master_seed", "requirement": "EXP-002"},
        )
    if replication_id < 0:
        raise ConfigurationValidationError(
            "replication ID must be nonnegative",
            {"field": "replication_id", "requirement": "EXP-006"},
        )
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", code_revision):
        raise ConfigurationValidationError(
            "code revision must be a 7-64 character hexadecimal Git object ID",
            {"field": "code_revision", "requirement": "EXP-006"},
        )
    if not model_profiles:
        raise ConfigurationValidationError(
            "run identity requires at least one model profile",
            {"field": "model_profiles", "requirement": "EXP-006"},
        )
    payload = {
        "code_revision": code_revision,
        "configuration_sha256": configuration_sha256,
        "experiment_factors": dict(sorted((experiment_factors or {}).items())),
        "identity_schema_version": "1.0",
        "master_seed": master_seed.lower(),
        "model_profiles": dict(sorted(model_profiles.items())),
        "replication_id": replication_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return RunIdentity(
        id=RunId(f"run/{digest}"),
        identity_schema_version="1.0",
        configuration_sha256=configuration_sha256,
        master_seed=master_seed.lower(),
        replication_id=replication_id,
        code_revision=code_revision,
        model_profiles=tuple(sorted(model_profiles.items())),
        experiment_factors=tuple(sorted((experiment_factors or {}).items())),
    )


def build_run_metadata(
    identity: RunIdentity,
    *,
    working_tree_dirty: bool,
    rng_streams: tuple[RngStreamRecord, ...],
) -> RunMetadata:
    """Capture diagnostics without contaminating the semantic run identity."""

    return RunMetadata(
        identity=identity,
        working_tree_dirty=working_tree_dirty,
        rng_streams=rng_streams,
        environment=environment_metadata(),
    )


def build_exogenous_configuration_sha256(scenario: NormalizedScenario) -> str:
    """Identify factors that must remain paired when scheduler policy changes.

    Scheduler configuration, scenario labels, and derived warnings are intentionally excluded.
    Radio, topology, traffic, timing, model profiles, and extensions remain covered.
    """

    payload = {
        "exogenous_identity_schema_version": "1.0",
        "simulation": scenario.simulation.model_dump(mode="python"),
        "radio": scenario.radio.model_dump(mode="python"),
        "models": scenario.models.model_dump(mode="python"),
        "topology": scenario.topology.model_dump(mode="python"),
        "traffic_profiles": {
            key: value.model_dump(mode="python")
            for key, value in sorted(scenario.traffic_profiles.items())
        },
        "extensions": scenario.extensions,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
