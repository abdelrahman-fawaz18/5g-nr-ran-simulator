from __future__ import annotations

from typing import Any

import pytest

from nr_ran_sim.config.models import ScenarioConfig
from nr_ran_sim.config.normalize import normalize_scenario
from nr_ran_sim.domain import BearerId, CellId, PacketId, UeId, build_entity_registry
from nr_ran_sim.errors import InvariantViolation


def test_entity_expansion_is_stable_and_typed(scenario_data: dict[str, Any]) -> None:
    group = scenario_data["topology"]["ue_groups"].pop("users")
    group["count"] = 2
    scenario_data["topology"]["ue_groups"] = {"z-group": group, "a-group": group}
    scenario = normalize_scenario(ScenarioConfig.model_validate(scenario_data))

    entities = build_entity_registry(scenario)

    assert entities.cells[0].id == CellId("cell/cell-a")
    assert [str(ue.id) for ue in entities.ues] == [
        "ue/a-group/000000",
        "ue/a-group/000001",
        "ue/z-group/000000",
        "ue/z-group/000001",
    ]
    assert [str(bearer.id) for bearer in entities.bearers] == [
        "bearer/a-group/000000/broadband",
        "bearer/a-group/000001/broadband",
        "bearer/z-group/000000/broadband",
        "bearer/z-group/000001/broadband",
    ]
    assert entities.bearer(entities.bearers[0].id) == entities.bearers[0]


def test_identifier_types_do_not_compare_equal() -> None:
    assert UeId("shared") != BearerId("shared")
    assert PacketId("packet/a") != CellId("packet/a")


@pytest.mark.parametrize("value", ["", "UPPER", "has space", "a" * 256])
def test_stable_identifier_rejects_invalid_values(value: str) -> None:
    with pytest.raises(InvariantViolation):
        UeId(value)


def test_registry_rejects_unknown_bearer(scenario_data: dict[str, Any]) -> None:
    scenario = normalize_scenario(ScenarioConfig.model_validate(scenario_data))
    with pytest.raises(InvariantViolation, match="not present"):
        build_entity_registry(scenario).bearer(BearerId("bearer/missing"))
