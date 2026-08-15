from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from nr_ran_sim.config import ScenarioConfig, load_scenario, normalize_scenario
from nr_ran_sim.errors import ArtifactError, ConfigurationValidationError
from nr_ran_sim.experiments.dynamic_simulation import run_dynamic_system_simulation
from nr_ran_sim.experiments.simulation import run_system_simulation

ROOT = Path(__file__).parents[2]
MASTER_SEED = "0x44444444444444444444444444444444"
REVISION = "b" * 40


def _data(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((ROOT / "examples" / "scenarios" / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _scenario(name: str):  # type: ignore[no-untyped-def]
    return normalize_scenario(ScenarioConfig.model_validate(_data(name)))


def _run(name: str):  # type: ignore[no-untyped-def]
    return run_dynamic_system_simulation(
        _scenario(name),
        master_seed=MASTER_SEED,
        replication_id=1,
        code_revision=REVISION,
        working_tree_dirty=False,
    )


def test_dynamic_fr1_run_is_replay_stable_reconstructable_and_handover_aware() -> None:
    first = _run("dynamic-fr1-mobility.yaml")
    replay = _run("dynamic-fr1-mobility.yaml")

    assert first.semantic_sha256 == replay.semantic_sha256
    assert first.semantic_dict() == replay.semantic_dict()
    assert len(first.radio_frames) == 20
    assert len(first.intervals) == 40
    assert first.radio_frames[0].previous_active_prbs == (
        ("cell/cell-a", 135),
        ("cell/cell-b", 135),
    )
    assert any(item.kind == "handover_executed" for item in first.handover_transitions)
    for frame in first.radio_frames:
        prior = dict(frame.previous_active_prbs)
        for state in frame.ue_states:
            for component in state.sinr.components:
                assert component.active_prbs == prior[component.cell_id]
                assert component.overlap_prbs == min(270, prior[component.cell_id])
    frames_by_tick = {frame.tick: frame for frame in first.radio_frames}
    for diagnostic in first.allocation_radio_diagnostics:
        prior = dict(frames_by_tick[diagnostic.start_tick].previous_active_prbs)
        for component in diagnostic.sinr.components:
            assert component.active_prbs == prior[component.cell_id]
            assert component.overlap_prbs == min(
                diagnostic.allocated_prbs, prior[component.cell_id]
            )
    interrupted = {
        (frame.tick, state.ue_id)
        for frame in first.radio_frames
        for state in frame.ue_states
        if state.handover_interruption
    }
    assert interrupted
    assert all(
        (interval.start_tick, ue_id) not in interrupted
        for interval in first.intervals
        for ue_id in interval.eligible_ue_ids
    )
    assert first.dynamic_kpis.definition_version == "dynamic-radio-1.0"
    assert all(record.run_id == str(first.identity.id) for record in first.dynamic_kpis.records)
    assert {record.aggregation_level for record in first.dynamic_kpis.records} == {"ue", "system"}


def test_scheduler_change_preserves_exogenous_motion_and_large_scale_channel() -> None:
    scenario = _scenario("dynamic-fr1-mobility.yaml")
    data = copy.deepcopy(_data("dynamic-fr1-mobility.yaml"))
    data["scheduler"] = {"policy": "round-robin", "parameters": {}}
    comparison = normalize_scenario(ScenarioConfig.model_validate(data))
    first = run_dynamic_system_simulation(
        scenario,
        master_seed=MASTER_SEED,
        replication_id=1,
        code_revision=REVISION,
        working_tree_dirty=False,
    )
    second = run_dynamic_system_simulation(
        comparison,
        master_seed=MASTER_SEED,
        replication_id=1,
        code_revision=REVISION,
        working_tree_dirty=False,
    )

    assert first.exogenous_configuration_sha256 == second.exogenous_configuration_sha256
    first_channel = [
        (
            frame.tick,
            state.ue_id,
            state.position,
            tuple((link.cell_id, link.path_loss) for link in state.links),
        )
        for frame in first.radio_frames
        for state in frame.ue_states
    ]
    second_channel = [
        (
            frame.tick,
            state.ue_id,
            state.position,
            tuple((link.cell_id, link.path_loss) for link in state.links),
        )
        for frame in second.radio_frames
        for state in frame.ue_states
    ]
    assert first_channel == second_channel
    assert first.semantic_sha256 != second.semantic_sha256


def test_fr2_run_exposes_beams_blockage_and_availability_transitions() -> None:
    result = _run("fr2-mobility-availability.yaml")
    states = [frame.ue_states[0] for frame in result.radio_frames]

    assert len(result.radio_frames) == 96
    assert {state.links[0].beam.beam_id for state in states if state.links[0].beam} == {"east"}
    assert (
        sum(bool(state.links[0].blockage and state.links[0].blockage.blocked) for state in states)
        == 32
    )
    assert [item.kind for item in result.availability_transitions] == [
        "outage_entered",
        "outage_recovered",
    ]
    assert any(state.outage for state in states)
    assert all(state.links[0].path_loss.carrier_frequency_hz == 28_000_000_000 for state in states)


@pytest.mark.parametrize(
    ("scs_khz", "bandwidth_mhz", "expected_prbs"),
    [
        (60, 50, 66),
        (60, 100, 132),
        (60, 200, 264),
        (120, 50, 32),
        (120, 100, 66),
        (120, 200, 132),
        (120, 400, 264),
    ],
)
def test_every_supported_fr2_1_resource_pair_resolves_exactly(
    scs_khz: int, bandwidth_mhz: int, expected_prbs: int
) -> None:
    data = _data("fr2-mobility-availability.yaml")
    data["radio"]["subcarrier_spacing"] = {"value": scs_khz, "unit": "kHz"}
    data["radio"]["channel_bandwidth"] = {"value": bandwidth_mhz, "unit": "MHz"}
    normalized = normalize_scenario(ScenarioConfig.model_validate(data))

    assert normalized.radio.prb_count == expected_prbs


@pytest.mark.parametrize("carrier_ghz", [24.25, 52.6])
def test_fr2_1_frequency_boundaries_are_inclusive(carrier_ghz: float) -> None:
    data = _data("fr2-mobility-availability.yaml")
    data["radio"]["carrier_frequency"] = {"value": carrier_ghz, "unit": "GHz"}
    assert normalize_scenario(ScenarioConfig.model_validate(data)).radio.frequency_range == "FR2-1"


def test_unsupported_fr2_resource_pair_fails_closed() -> None:
    data = _data("fr2-mobility-availability.yaml")
    data["radio"]["subcarrier_spacing"] = {"value": 60, "unit": "kHz"}
    data["radio"]["channel_bandwidth"] = {"value": 400, "unit": "MHz"}
    with pytest.raises(ConfigurationValidationError, match="unsupported FR2-1"):
        normalize_scenario(ScenarioConfig.model_validate(data))


def test_dynamic_artifact_collision_is_safe(tmp_path: Path) -> None:
    result = _run("dynamic-fr1-mobility.yaml")
    target = tmp_path / "dynamic.json"
    result.write(target)
    with pytest.raises(ArtifactError, match="already exists"):
        result.write(target)
    result.write(target, force=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_extension", "requires extensions"),
        ("wrong_interference", "activity-coupled"),
        ("missing_correlation", "correlation distance"),
        ("high_uma_ue", "at or below 13 m"),
    ],
)
def test_dynamic_profile_rejects_incomplete_model_contract(mutation: str, message: str) -> None:
    data = copy.deepcopy(_data("dynamic-fr1-mobility.yaml"))
    if mutation == "missing_extension":
        data["extensions"] = {}
    elif mutation == "wrong_interference":
        data["models"]["interference"] = "noise_limited-v1"
    elif mutation == "missing_correlation":
        data["extensions"]["nr-ran-sim.dynamic-radio"]["channel"]["shadow_correlation_distance"] = (
            None
        )
    else:
        data["topology"]["ue_groups"]["movers"]["placement"]["positions"][0]["z"] = {
            "value": 14,
            "unit": "m",
        }
    with pytest.raises(ConfigurationValidationError, match=message):
        normalize_scenario(ScenarioConfig.model_validate(data))


def test_approved_static_result_remains_exactly_unchanged() -> None:
    scenario = normalize_scenario(
        load_scenario(ROOT / "examples" / "scenarios" / "scheduler-qos-smoke.yaml")
    )
    result = run_system_simulation(
        scenario,
        master_seed="0x11111111111111111111111111111111",
        replication_id=0,
        code_revision="47909b24fb55fd0423a4b5dc67047f1e911d5c4f",
        working_tree_dirty=False,
    )

    assert result.configuration_manifest.configuration_sha256 == (
        "4462afc012438a0f6eca202aefbb2c8051d9c57ee53e6ca013f190ec28c70f83"
    )
    assert result.exogenous_configuration_sha256 == (
        "95fe1fd4767eb6e8fc0f8ae40386bb81f2d529563e5ad8cd47b1474dbec7dd9c"
    )
    assert result.radio_snapshot.semantic_sha256 == (
        "3c308d12b599db9a3f47c5dae558d1352a6932bc71d5524e96f55ad9e60d824b"
    )
    assert result.semantic_sha256 == (
        "a7aa72e5629e6352ff8ea23f0bed9e0dc69cf26c0bfec733f87a0448a16d4c69"
    )
