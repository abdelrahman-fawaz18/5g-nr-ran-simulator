from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from nr_ran_sim.config.models import ScenarioConfig


def test_valid_scenario_is_frozen_and_expands_defaults(scenario_data: dict[str, Any]) -> None:
    config = ScenarioConfig.model_validate(scenario_data)
    assert config.extensions == {}
    assert config.topology.ue_groups["users"].placement.attempt_budget == 10_000
    with pytest.raises(ValidationError):
        config.scenario_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update({"unknown": 1}), "Extra inputs are not permitted"),
        (lambda data: data.update({"scenario_id": "Bad ID"}), "String should match pattern"),
        (lambda data: data["radio"].update({"target_bler": 0.2}), "target_bler"),
        (
            lambda data: data["traffic_profiles"]["broadband"].update(
                {"queue": {"max_packets": None, "max_payload": None}}
            ),
            "queue must define",
        ),
        (
            lambda data: data["scheduler"].update(
                {"policy": "round-robin", "parameters": {"averaging_alpha": 0.1}}
            ),
            "accepts no tuning parameters",
        ),
        (
            lambda data: data["scheduler"].update(
                {"policy": "proportional-fair", "parameters": {}}
            ),
            "proportional-fair requires",
        ),
        (
            lambda data: data["topology"]["ue_groups"]["users"].update({"bearers": ["missing"]}),
            "references unknown bearers",
        ),
    ],
)
def test_structural_contract_rejects_invalid_input(
    scenario_data: dict[str, Any],
    mutation: Any,
    message: str,
) -> None:
    mutation(scenario_data)
    with pytest.raises(ValidationError, match=message):
        ScenarioConfig.model_validate(scenario_data)
