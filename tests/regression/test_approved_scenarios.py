from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from nr_ran_sim.config import build_manifest, load_scenario, normalize_scenario
from nr_ran_sim.experiments.dynamic_simulation import run_dynamic_system_simulation
from nr_ran_sim.experiments.simulation import run_system_simulation
from nr_ran_sim.radio.capacity_snapshot import build_capacity_snapshot
from nr_ran_sim.radio.snapshot import build_radio_snapshot

ROOT = Path(__file__).parents[2]
CATALOGUE = ROOT / "tests" / "regression" / "approved_scenarios.yaml"


def _cases() -> list[dict[str, Any]]:
    payload = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    assert payload["approval"]["purpose"].endswith("not independent verification or calibration")
    return payload["cases"]


@pytest.mark.regression
@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["id"])
def test_approved_scenario_semantics_remain_exact(case: dict[str, Any]) -> None:
    scenario = normalize_scenario(load_scenario(ROOT / case["scenario"]))
    expected = case["expected"]
    assert build_manifest(scenario).configuration_sha256 == expected["configuration_sha256"]

    if case["kind"] == "radio_snapshot":
        result = build_radio_snapshot(
            scenario,
            master_seed=case["master_seed"],
            replication_id=case["replication_id"],
        )
    elif case["kind"] == "capacity_snapshot":
        result = build_capacity_snapshot(
            scenario,
            master_seed=case["master_seed"],
            replication_id=case["replication_id"],
        )
        assert result.radio_snapshot_sha256 == expected["parent_radio_sha256"]
    else:
        runner = (
            run_system_simulation
            if case["kind"] == "static_simulation"
            else run_dynamic_system_simulation
        )
        result = runner(
            scenario,
            master_seed=case["master_seed"],
            replication_id=case["replication_id"],
            code_revision=case["code_revision"],
            working_tree_dirty=False,
        )
        assert result.exogenous_configuration_sha256 == expected["exogenous_sha256"]

    assert result.semantic_sha256 == expected["semantic_sha256"]
