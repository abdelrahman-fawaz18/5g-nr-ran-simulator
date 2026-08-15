"""Immutable, visualization-ready static radio scene and link diagnostics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from nr_ran_sim.config.manifest import build_manifest
from nr_ran_sim.config.normalize import NormalizedScenario
from nr_ran_sim.errors import ArtifactError, InvariantViolation
from nr_ran_sim.experiments.seeds import RngStreamRecord, SemanticRngRegistry
from nr_ran_sim.radio.geometry import LinkGeometry, link_geometry
from nr_ran_sim.radio.link import (
    InterferenceResult,
    LinkBudgetResult,
    NoiseResult,
    SinrResult,
    aggregate_interference,
    calculate_link_budget,
    calculate_sinr,
    thermal_noise,
)
from nr_ran_sim.radio.propagation import (
    LosSelectionResult,
    PathLossResult,
    PropagationState,
    Scenario,
    draw_static_shadow_fading_db,
    evaluate_path_loss,
    select_effective_environment_height_m,
    select_los_state,
)
from nr_ran_sim.radio.topology import RadioTopology, build_radio_topology

RADIO_SNAPSHOT_SCHEMA_VERSION = "1.0"
RADIO_SNAPSHOT_SIGNIFICANT_DIGITS = 12


@dataclass(frozen=True, slots=True)
class RadioLinkObservation:
    id: str
    cell_id: str
    ue_id: str
    geometry: LinkGeometry
    los_selection: LosSelectionResult
    path_loss: PathLossResult
    link_budget: LinkBudgetResult

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "cell_id": self.cell_id,
            "ue_id": self.ue_id,
            "geometry": self.geometry.as_dict(),
            "los_selection": self.los_selection.as_dict(),
            "path_loss": self.path_loss.as_dict(),
            "link_budget": self.link_budget.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ServingAssociation:
    ue_id: str
    serving_cell_id: str
    association_rule: str
    serving_reference_signal_received_power_dbm: float
    noise: NoiseResult
    interference: InterferenceResult
    sinr: SinrResult

    def as_dict(self) -> dict[str, object]:
        return {
            "ue_id": self.ue_id,
            "serving_cell_id": self.serving_cell_id,
            "association_rule": self.association_rule,
            "serving_reference_signal_received_power_dbm": (
                self.serving_reference_signal_received_power_dbm
            ),
            "noise": self.noise.as_dict(),
            "interference": self.interference.as_dict(),
            "sinr": self.sinr.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class RadioSnapshot:
    schema_version: str
    semantic_sha256: str
    configuration_sha256: str
    master_seed: str
    replication_id: int
    scenario_id: str
    coordinate_system: str
    scenario: str
    model_profiles: dict[str, str]
    topology: RadioTopology
    links: tuple[RadioLinkObservation, ...]
    associations: tuple[ServingAssociation, ...]
    rng_streams: tuple[RngStreamRecord, ...]

    def as_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "configuration_sha256": self.configuration_sha256,
            "master_seed": self.master_seed,
            "replication_id": self.replication_id,
            "scenario_id": self.scenario_id,
            "coordinate_system": self.coordinate_system,
            "scenario": self.scenario,
            "model_profiles": dict(sorted(self.model_profiles.items())),
            "topology": self.topology.as_dict(),
            "links": [link.as_dict() for link in self.links],
            "associations": [association.as_dict() for association in self.associations],
            "rng_streams": [_rng_record_dict(record) for record in self.rng_streams],
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
                "output radio snapshot already exists; pass --force to replace it",
                {"path": str(path)},
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_text(self.to_json(), encoding="utf-8", newline="\n")
            temporary.replace(path)
        except OSError as exc:
            raise ArtifactError(
                "unable to commit radio snapshot",
                {"path": str(path), "detail": str(exc)},
            ) from exc
        finally:
            if temporary.exists():
                temporary.unlink()


def build_radio_snapshot(
    scenario: NormalizedScenario,
    *,
    master_seed: str,
    replication_id: int,
    randomness_baseline_id: str | None = None,
) -> RadioSnapshot:
    """Build one static scene whose exported terms reconstruct every UE SINR."""

    manifest = build_manifest(scenario)
    registry = SemanticRngRegistry(
        manifest.configuration_sha256 if randomness_baseline_id is None else randomness_baseline_id,
        master_seed,
        replication_id,
    )
    topology = build_radio_topology(scenario, registry)
    links = tuple(
        _evaluate_link(scenario, topology, cell_index, ue_index, registry)
        for ue_index in range(len(topology.ues))
        for cell_index in range(len(topology.cells))
    )
    associations = tuple(
        _associate_ue(scenario, ue.id, ue.receiver_noise_figure_db, links) for ue in topology.ues
    )
    snapshot = RadioSnapshot(
        schema_version=RADIO_SNAPSHOT_SCHEMA_VERSION,
        semantic_sha256="",
        configuration_sha256=manifest.configuration_sha256,
        master_seed=master_seed.lower(),
        replication_id=replication_id,
        scenario_id=scenario.scenario_id,
        coordinate_system=topology.coordinate_system,
        scenario=scenario.topology.scenario,
        model_profiles={
            "fidelity": scenario.models.fidelity_profile,
            "propagation": scenario.models.propagation,
            "los_state": scenario.models.los_state,
            "shadowing": scenario.models.shadowing,
            "interference": scenario.models.interference,
        },
        topology=topology,
        links=links,
        associations=associations,
        rng_streams=registry.manifest(),
    )
    digest = hashlib.sha256(_semantic_bytes(snapshot)).hexdigest()
    return RadioSnapshot(
        schema_version=snapshot.schema_version,
        semantic_sha256=digest,
        configuration_sha256=snapshot.configuration_sha256,
        master_seed=snapshot.master_seed,
        replication_id=snapshot.replication_id,
        scenario_id=snapshot.scenario_id,
        coordinate_system=snapshot.coordinate_system,
        scenario=snapshot.scenario,
        model_profiles=snapshot.model_profiles,
        topology=snapshot.topology,
        links=snapshot.links,
        associations=snapshot.associations,
        rng_streams=snapshot.rng_streams,
    )


def _evaluate_link(
    scenario: NormalizedScenario,
    topology: RadioTopology,
    cell_index: int,
    ue_index: int,
    registry: SemanticRngRegistry,
) -> RadioLinkObservation:
    cell = topology.cells[cell_index]
    ue = topology.ues[ue_index]
    geometry = link_geometry(cell.position, ue.position)
    stream_root = f"link/{cell.configuration_id}/{ue.id}"
    explicit_state = _explicit_state(scenario, cell.configuration_id, ue.group_id, ue.ordinal)
    los_rng = (
        None
        if scenario.models.los_state == "explicit"
        else registry.acquire(f"{stream_root}/los", owner=f"los-state:{cell.id}:{ue.id}")
    )
    los_selection = select_los_state(
        cast(Scenario, scenario.topology.scenario),
        geometry.horizontal_distance_m,
        ue.position.z_m,
        mode=cast(Literal["explicit", "probability_static"], scenario.models.los_state),
        explicit_state=explicit_state,
        rng=los_rng,
    )
    needs_environment_rng = (
        scenario.topology.scenario == "uma"
        and ue.position.z_m > 13.0
        and geometry.horizontal_distance_m > 18.0
    )
    environment_rng = (
        registry.acquire(
            f"{stream_root}/effective-environment-height",
            owner=f"effective-environment-height:{cell.id}:{ue.id}",
        )
        if needs_environment_rng
        else None
    )
    effective_environment_height = select_effective_environment_height_m(
        cast(Scenario, scenario.topology.scenario),
        geometry.horizontal_distance_m,
        ue.position.z_m,
        rng=environment_rng,
    )
    path_loss = evaluate_path_loss(
        cast(Scenario, scenario.topology.scenario),
        los_selection.state,
        geometry,
        float(scenario.radio.carrier_frequency_hz),
        effective_environment_height_m=effective_environment_height,
        average_building_height_m=(
            None
            if scenario.topology.average_building_height_m is None
            else float(scenario.topology.average_building_height_m)
        ),
        average_street_width_m=(
            None
            if scenario.topology.average_street_width_m is None
            else float(scenario.topology.average_street_width_m)
        ),
    )
    shadow_rng = (
        None
        if scenario.models.shadowing == "off"
        else registry.acquire(
            f"{stream_root}/shadow",
            owner=f"static-shadow:{cell.id}:{ue.id}",
        )
    )
    path_loss = path_loss.with_shadow(draw_static_shadow_fading_db(path_loss, shadow_rng))
    budget = calculate_link_budget(
        cell,
        ue,
        path_loss,
        transmission_bandwidth_hz=scenario.radio.transmission_bandwidth_hz,
        subcarrier_spacing_hz=scenario.radio.subcarrier_spacing_hz,
    )
    return RadioLinkObservation(
        id=f"link/{cell.configuration_id}/{ue.id}",
        cell_id=cell.id,
        ue_id=ue.id,
        geometry=geometry,
        los_selection=los_selection,
        path_loss=path_loss,
        link_budget=budget,
    )


def _explicit_state(
    scenario: NormalizedScenario,
    cell_configuration_id: str,
    group_id: str,
    ordinal: int,
) -> PropagationState | None:
    if scenario.models.los_state != "explicit":
        return None
    states = scenario.topology.ue_groups[group_id].explicit_link_states
    if states is None or cell_configuration_id not in states:
        raise InvariantViolation(
            "normalized explicit LOS state is missing",
            {
                "cell_id": cell_configuration_id,
                "group_id": group_id,
                "ordinal": ordinal,
                "requirement": "PROP-006",
            },
        )
    return cast(PropagationState, states[cell_configuration_id][ordinal])


def _associate_ue(
    scenario: NormalizedScenario,
    ue_id: str,
    receiver_noise_figure_db: float,
    all_links: tuple[RadioLinkObservation, ...],
) -> ServingAssociation:
    ue_links = tuple(link for link in all_links if link.ue_id == ue_id)
    if not ue_links:
        raise InvariantViolation(
            "UE has no evaluated cell links",
            {"ue_id": ue_id, "requirement": "PROP-010"},
        )
    serving = sorted(
        ue_links,
        key=lambda link: (
            -link.link_budget.reference_signal_received_power_dbm,
            link.cell_id,
        ),
    )[0]
    budgets = tuple(link.link_budget for link in ue_links)
    noise = thermal_noise(
        scenario.radio.transmission_bandwidth_hz,
        receiver_noise_figure_db,
    )
    interference = aggregate_interference(
        cast(
            Literal["noise_limited-v1", "full_buffer_reuse1-v1"],
            scenario.models.interference,
        ),
        serving.cell_id,
        budgets,
    )
    sinr = calculate_sinr(serving.link_budget, noise, interference)
    return ServingAssociation(
        ue_id=ue_id,
        serving_cell_id=serving.cell_id,
        association_rule="max-long-term-rsrp-lexical-tie-v1",
        serving_reference_signal_received_power_dbm=(
            serving.link_budget.reference_signal_received_power_dbm
        ),
        noise=noise,
        interference=interference,
        sinr=sinr,
    )


def _rng_record_dict(record: RngStreamRecord) -> dict[str, object]:
    return {
        "semantic_path": record.semantic_path,
        "owner": record.owner,
        "engine": record.engine,
        "numpy_version": record.numpy_version,
        "derivation_version": record.derivation_version,
        "fingerprint": record.fingerprint,
        "seed_words": list(record.seed_words),
    }


def _semantic_bytes(snapshot: RadioSnapshot) -> bytes:
    return json.dumps(
        canonicalize_floats(snapshot.as_dict(include_digest=False)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonicalize_floats(value: object) -> object:
    """Remove insignificant libm differences from the portable JSON contract."""

    if isinstance(value, float):
        canonical = float(format(value, f".{RADIO_SNAPSHOT_SIGNIFICANT_DIGITS}g"))
        return 0.0 if canonical == 0.0 else canonical
    if isinstance(value, dict):
        return {key: canonicalize_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonicalize_floats(item) for item in value]
    if isinstance(value, tuple):
        return [canonicalize_floats(item) for item in value]
    return value
