from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from nr_ran_sim.config import load_scenario, normalize_scenario
from nr_ran_sim.config.models import ScenarioConfig
from nr_ran_sim.errors import ArtifactError, ModelDomainError
from nr_ran_sim.radio.snapshot import (
    RADIO_SNAPSHOT_SIGNIFICANT_DIGITS,
    build_radio_snapshot,
    canonicalize_floats,
)

MASTER_SEED = "0x11111111111111111111111111111111"
ROOT = Path(__file__).parents[2]
MULTICELL = ROOT / "examples" / "scenarios" / "uma-multicell-radio.yaml"


def _normalized(data: dict[str, Any]):  # type: ignore[no-untyped-def]
    return normalize_scenario(ScenarioConfig.model_validate(data))


def test_multicell_snapshot_is_deterministic_and_visualization_ready() -> None:
    scenario = normalize_scenario(load_scenario(MULTICELL))
    first = build_radio_snapshot(scenario, master_seed=MASTER_SEED, replication_id=4)
    replay = build_radio_snapshot(scenario, master_seed=MASTER_SEED, replication_id=4)
    changed_seed = build_radio_snapshot(
        scenario,
        master_seed="0x22222222222222222222222222222222",
        replication_id=4,
    )
    assert first.to_json() == replay.to_json()
    assert first.semantic_sha256 == replay.semantic_sha256
    assert first.semantic_sha256 != changed_seed.semantic_sha256
    assert len(first.topology.cells) == 3
    assert len(first.topology.ues) == 12
    assert len(first.links) == 36
    assert len(first.associations) == 12
    assert first.schema_version == "1.0"
    assert first.model_profiles["interference"] == "full_buffer_reuse1-v1"
    payload = json.loads(first.to_json())
    assert payload["semantic_sha256"] == first.semantic_sha256
    assert payload["coordinate_system"] == "local-cartesian"


def test_snapshot_canonicalization_removes_last_bit_platform_noise() -> None:
    assert RADIO_SNAPSHOT_SIGNIFICANT_DIGITS == 12
    assert canonicalize_floats(
        {"positive": 83.13815667685238, "small": [1.234567890123456e-18]}
    ) == canonicalize_floats({"positive": 83.1381566768524, "small": [1.234567890123458e-18]})
    assert json.dumps(canonicalize_floats(-0.0)) == "0.0"


def test_every_exported_association_reconstructs_received_power_and_sinr() -> None:
    scenario = normalize_scenario(load_scenario(MULTICELL))
    snapshot = build_radio_snapshot(scenario, master_seed=MASTER_SEED, replication_id=0)
    links = {(link.cell_id, link.ue_id): link for link in snapshot.links}
    for association in snapshot.associations:
        serving = links[(association.serving_cell_id, association.ue_id)]
        budget = serving.link_budget
        reconstructed_received_dbm = (
            budget.transmit_power_dbm
            + budget.transmitter_gain_dbi
            + budget.receiver_gain_dbi
            - budget.basic_path_loss_db
            - budget.shadow_fading_db
            - budget.penetration_loss_db
            - budget.miscellaneous_loss_db
        )
        assert budget.received_power_dbm == pytest.approx(reconstructed_received_dbm, abs=1e-12)
        reconstructed_sinr = association.sinr.signal_power_w / (
            association.sinr.interference_power_w + association.sinr.noise_power_w
        )
        assert association.sinr.sinr_linear == pytest.approx(reconstructed_sinr, rel=1e-12)
        assert len(association.interference.components) == 2
        assert association.serving_reference_signal_received_power_dbm == (
            budget.reference_signal_received_power_dbm
        )

    exported = json.loads(snapshot.to_json())
    exported_links = {(link["cell_id"], link["ue_id"]): link for link in exported["links"]}
    for association in exported["associations"]:
        budget = exported_links[(association["serving_cell_id"], association["ue_id"])][
            "link_budget"
        ]
        reconstructed_received_dbm = (
            budget["transmit_power_dbm"]
            + budget["transmitter_gain_dbi"]
            + budget["receiver_gain_dbi"]
            - budget["basic_path_loss_db"]
            - budget["shadow_fading_db"]
            - budget["penetration_loss_db"]
            - budget["miscellaneous_loss_db"]
        )
        assert budget["received_power_dbm"] == pytest.approx(reconstructed_received_dbm, abs=1e-9)
        sinr = association["sinr"]
        reconstructed_sinr = sinr["signal_power_w"] / (
            sinr["interference_power_w"] + sinr["noise_power_w"]
        )
        assert sinr["sinr_linear"] == pytest.approx(reconstructed_sinr, rel=1e-9)


def test_noise_limited_profile_exports_zero_interference() -> None:
    scenario = normalize_scenario(
        load_scenario(ROOT / "examples" / "scenarios" / "uma-fr1-foundation.yaml")
    )
    snapshot = build_radio_snapshot(scenario, master_seed=MASTER_SEED, replication_id=0)
    assert all(item.interference.total_power_w == 0.0 for item in snapshot.associations)
    assert all(item.interference.total_power_dbm is None for item in snapshot.associations)


def test_exact_association_tie_selects_lexically_smallest_cell(
    scenario_data: dict[str, Any],
) -> None:
    data = copy.deepcopy(scenario_data)
    data["models"].update(
        {"los_state": "explicit", "shadowing": "off", "interference": "full_buffer_reuse1-v1"}
    )
    cell_template = data["topology"]["cells"].pop("cell-a")
    cell_a = copy.deepcopy(cell_template)
    cell_a["position"]["x"] = {"value": -100, "unit": "m"}
    cell_b = copy.deepcopy(cell_template)
    cell_b["position"]["x"] = {"value": 100, "unit": "m"}
    data["topology"]["cells"] = {"cell-b": cell_b, "cell-a": cell_a}
    group = data["topology"]["ue_groups"]["users"]
    group["count"] = 1
    group["explicit_link_states"] = {"cell-a": ["los"], "cell-b": ["los"]}
    group["placement"] = {
        "mode": "explicit",
        "positions": [
            {
                "x": {"value": 0, "unit": "m"},
                "y": {"value": 100, "unit": "m"},
                "z": {"value": 1.5, "unit": "m"},
            }
        ],
        "minimum_2d_distance": {"value": 10, "unit": "m"},
    }
    snapshot = build_radio_snapshot(_normalized(data), master_seed=MASTER_SEED, replication_id=0)
    association = snapshot.associations[0]
    assert association.serving_cell_id == "cell/cell-a"
    assert association.association_rule == "max-long-term-rsrp-lexical-tie-v1"


def test_snapshot_write_is_atomic_and_collision_safe(tmp_path: Path) -> None:
    scenario = normalize_scenario(load_scenario(MULTICELL))
    snapshot = build_radio_snapshot(scenario, master_seed=MASTER_SEED, replication_id=0)
    target = tmp_path / "nested" / "radio.json"
    snapshot.write(target)
    assert json.loads(target.read_text(encoding="utf-8"))["semantic_sha256"] == (
        snapshot.semantic_sha256
    )
    with pytest.raises(ArtifactError, match="already exists"):
        snapshot.write(target)
    snapshot.write(target, force=True)


def test_snapshot_fails_before_simulation_when_any_link_is_outside_model_domain(
    scenario_data: dict[str, Any],
) -> None:
    data = copy.deepcopy(scenario_data)
    group = data["topology"]["ue_groups"]["users"]
    group["count"] = 1
    group["placement"] = {
        "mode": "explicit",
        "positions": [
            {
                "x": {"value": 5000.001, "unit": "m"},
                "y": {"value": 0, "unit": "m"},
                "z": {"value": 1.5, "unit": "m"},
            }
        ],
        "minimum_2d_distance": {"value": 10, "unit": "m"},
    }
    with pytest.raises(ModelDomainError) as raised:
        build_radio_snapshot(_normalized(data), master_seed=MASTER_SEED, replication_id=0)
    assert raised.value.context["field"] == "horizontal_distance_m"


def test_multicell_example_is_valid_yaml_mapping() -> None:
    loaded = yaml.safe_load(MULTICELL.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    assert loaded["models"]["interference"] == "full_buffer_reuse1-v1"
