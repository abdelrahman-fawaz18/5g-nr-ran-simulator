from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import ValidationError

from nr_ran_sim.config.manifest import build_manifest
from nr_ran_sim.config.models import ScenarioConfig
from nr_ran_sim.config.normalize import NormalizedExplicitPlacement, normalize_scenario
from nr_ran_sim.errors import ConfigurationValidationError, ModelDomainError, RunExecutionError
from nr_ran_sim.experiments.seeds import SemanticRngRegistry
from nr_ran_sim.radio.geometry import Position3D, link_geometry
from nr_ran_sim.radio.topology import build_radio_topology

MASTER_SEED = "0x0123456789abcdef0123456789abcdef"


def _normalized(data: dict[str, Any]) -> Any:
    return normalize_scenario(ScenarioConfig.model_validate(data))


def _registry(normalized: Any) -> SemanticRngRegistry:
    return SemanticRngRegistry(build_manifest(normalized).configuration_sha256, MASTER_SEED, 2)


def test_geometry_reference_vector_exposes_2d_and_3d_distance() -> None:
    geometry = link_geometry(Position3D(0.0, 0.0, 25.0), Position3D(300.0, 400.0, 1.5))
    assert geometry.horizontal_distance_m == 500.0
    assert geometry.height_difference_m == 23.5
    assert geometry.direct_distance_m == pytest.approx(math.sqrt(500.0**2 + 23.5**2), rel=1e-12)
    assert geometry.as_dict()["receiver"] == {"x_m": 300.0, "y_m": 400.0, "z_m": 1.5}


def test_geometry_rejects_nonfinite_coordinate() -> None:
    with pytest.raises(ModelDomainError, match="finite") as raised:
        Position3D(math.nan, 0.0, 1.5)
    assert raised.value.context["requirement"] == "PROP-001"


def test_seeded_topology_replays_and_unrelated_ue_does_not_perturb_existing(
    scenario_data: dict[str, Any],
) -> None:
    baseline = _normalized(scenario_data)
    first = build_radio_topology(baseline, _registry(baseline))
    second = build_radio_topology(baseline, _registry(baseline))
    assert first == second
    assert first.as_dict()["coordinate_system"] == "local-cartesian"
    assert all(ue.placement_attempts >= 1 for ue in first.ues)

    scenario_data["topology"]["ue_groups"]["users"]["count"] += 1
    expanded = _normalized(scenario_data)
    expanded_topology = build_radio_topology(expanded, _registry(expanded))
    # Baseline/config digest changes by design, so use identical baseline ID to test semantic paths.
    same_baseline_registry = SemanticRngRegistry(
        build_manifest(baseline).configuration_sha256,
        MASTER_SEED,
        2,
    )
    expanded_with_paired_seed = build_radio_topology(expanded, same_baseline_registry)
    assert [ue.position for ue in expanded_with_paired_seed.ues[: len(first.ues)]] == [
        ue.position for ue in first.ues
    ]
    assert len(expanded_topology.ues) == len(first.ues) + 1


def test_explicit_topology_is_retained_without_rng_position_streams(
    scenario_data: dict[str, Any],
) -> None:
    group = scenario_data["topology"]["ue_groups"]["users"]
    group["count"] = 2
    group["placement"] = {
        "mode": "explicit",
        "positions": [
            {
                "x": {"value": 100, "unit": "m"},
                "y": {"value": 0, "unit": "m"},
                "z": {"value": 1.5, "unit": "m"},
            },
            {
                "x": {"value": 200, "unit": "m"},
                "y": {"value": 50, "unit": "m"},
                "z": {"value": 1.5, "unit": "m"},
            },
        ],
        "minimum_2d_distance": {"value": 10, "unit": "m"},
    }
    normalized = _normalized(scenario_data)
    assert isinstance(normalized.topology.ue_groups["users"].placement, NormalizedExplicitPlacement)
    registry = _registry(normalized)
    topology = build_radio_topology(normalized, registry)
    assert [ue.position.x_m for ue in topology.ues] == [100.0, 200.0]
    assert [ue.placement_attempts for ue in topology.ues] == [0, 0]
    assert registry.manifest() == ()


def test_explicit_placement_count_and_minimum_distance_fail_closed(
    scenario_data: dict[str, Any],
) -> None:
    group = scenario_data["topology"]["ue_groups"]["users"]
    group["count"] = 2
    group["placement"] = {
        "mode": "explicit",
        "positions": [
            {
                "x": {"value": 1, "unit": "m"},
                "y": {"value": 0, "unit": "m"},
                "z": {"value": 1.5, "unit": "m"},
            }
        ],
        "minimum_2d_distance": {"value": 10, "unit": "m"},
    }
    with pytest.raises(ValidationError, match="exactly 2 positions"):
        ScenarioConfig.model_validate(scenario_data)

    group["count"] = 1
    with pytest.raises(ConfigurationValidationError, match="minimum 2D"):
        _normalized(scenario_data)


def test_infeasible_random_topology_exhausts_bounded_attempt_budget(
    scenario_data: dict[str, Any],
) -> None:
    group = scenario_data["topology"]["ue_groups"]["users"]
    group["count"] = 1
    group["placement"].update(
        {
            "x_min": {"value": 1, "unit": "m"},
            "x_max": {"value": 2, "unit": "m"},
            "y_min": {"value": 1, "unit": "m"},
            "y_max": {"value": 2, "unit": "m"},
            "minimum_2d_distance": {"value": 10, "unit": "m"},
            "attempt_budget": 3,
        }
    )
    normalized = _normalized(scenario_data)
    with pytest.raises(RunExecutionError, match="attempt budget") as raised:
        build_radio_topology(normalized, _registry(normalized))
    assert raised.value.context["attempt_budget"] == 3


def test_explicit_los_state_contract_is_per_cell_and_per_ue(
    scenario_data: dict[str, Any],
) -> None:
    scenario_data["models"]["los_state"] = "explicit"
    group = scenario_data["topology"]["ue_groups"]["users"]
    with pytest.raises(ValidationError, match="requires explicit_link_states"):
        ScenarioConfig.model_validate(scenario_data)

    group["explicit_link_states"] = {"cell-a": ["los"]}
    with pytest.raises(ValidationError, match="exactly 20 entries"):
        ScenarioConfig.model_validate(scenario_data)

    group["explicit_link_states"] = {"wrong-cell": ["los"] * 20}
    with pytest.raises(ValidationError, match="configured cells"):
        ScenarioConfig.model_validate(scenario_data)

    scenario_data["models"]["los_state"] = "probability_static"
    with pytest.raises(ValidationError, match="must omit"):
        ScenarioConfig.model_validate(scenario_data)


def test_scenario_specific_environment_and_height_domains(scenario_data: dict[str, Any]) -> None:
    scenario_data["topology"]["scenario"] = "rma"
    scenario_data["topology"]["cells"]["cell-a"]["position"]["z"] = {
        "value": 35,
        "unit": "m",
    }
    with pytest.raises(ValidationError, match=r"requires topology\.propagation_environment"):
        ScenarioConfig.model_validate(scenario_data)

    scenario_data["topology"]["propagation_environment"] = {
        "average_building_height": {"value": 5, "unit": "m"},
        "average_street_width": {"value": 20, "unit": "m"},
    }
    normalized = _normalized(scenario_data)
    assert normalized.topology.average_building_height_m == 5

    scenario_data["topology"]["propagation_environment"]["average_street_width"] = {
        "value": 51,
        "unit": "m",
    }
    with pytest.raises(ConfigurationValidationError, match="5-50"):
        _normalized(scenario_data)

    scenario_data["topology"]["scenario"] = "umi_street_canyon"
    with pytest.raises(ValidationError, match="only valid for RMa"):
        ScenarioConfig.model_validate(scenario_data)


@pytest.mark.parametrize(
    ("scenario", "cell_height", "ue_height"),
    [("uma", 24, 1.5), ("umi_street_canyon", 9, 1.5), ("rma", 35, 10.1)],
)
def test_invalid_scenario_antenna_height_is_actionable(
    scenario_data: dict[str, Any],
    scenario: str,
    cell_height: float,
    ue_height: float,
) -> None:
    topology = scenario_data["topology"]
    topology["scenario"] = scenario
    topology["cells"]["cell-a"]["position"]["z"] = {"value": cell_height, "unit": "m"}
    topology["ue_groups"]["users"]["placement"]["height"] = {
        "value": ue_height,
        "unit": "m",
    }
    if scenario == "rma":
        topology["propagation_environment"] = {
            "average_building_height": {"value": 5, "unit": "m"},
            "average_street_width": {"value": 20, "unit": "m"},
        }
    with pytest.raises(ConfigurationValidationError) as raised:
        _normalized(scenario_data)
    assert raised.value.context["requirement"] == "PROP-004"
