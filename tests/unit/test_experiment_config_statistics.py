from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml
from tests.conftest import REPOSITORY_ROOT

from nr_ran_sim.errors import ConfigurationValidationError
from nr_ran_sim.experiments.config import ExperimentConfig, expand_variants, load_experiment
from nr_ran_sim.experiments.seeds import SemanticRngRegistry
from nr_ran_sim.experiments.statistics import _bootstrap_interval, _type7_quantile

SMOKE = REPOSITORY_ROOT / "examples" / "experiments" / "scheduler-comparison-smoke.yaml"


def test_experiment_schema_expands_scheduler_and_load_factors() -> None:
    source = load_experiment(
        REPOSITORY_ROOT / "examples" / "experiments" / "scheduler-comparison-study.yaml"
    )
    variants = expand_variants(source)
    assert len(variants) == 12
    assert len({item.variant_id for item in variants}) == 12
    assert len({item.configuration_sha256 for item in variants}) == 12
    assert {item.factors_dict()["scheduler"] for item in variants} == {
        "round-robin",
        "max-ci",
        "proportional-fair",
    }
    assert {item.factors_dict()["offered-load"] for item in variants} == {
        "low",
        "medium",
        "saturation",
        "overload",
    }


def test_experiment_rejects_duplicate_replications_and_reserved_pointer() -> None:
    data = yaml.safe_load(SMOKE.read_text(encoding="utf-8"))
    duplicate = copy.deepcopy(data)
    duplicate["seed_plan"]["replication_ids"] = [0, 0]
    with pytest.raises(ValueError, match="unique"):
        ExperimentConfig.model_validate(duplicate)

    reserved = copy.deepcopy(data)
    reserved["sweep_factors"] = [
        {
            "factor_id": "bad",
            "json_pointer": "/scheduler",
            "levels": [
                {"level_id": "one", "value": {}},
                {"level_id": "two", "value": {}},
            ],
        }
    ]
    with pytest.raises(ValueError, match="not valid generic sweep targets"):
        ExperimentConfig.model_validate(reserved)


def test_normalized_sweep_collision_is_rejected(tmp_path: Path) -> None:
    data = yaml.safe_load(SMOKE.read_text(encoding="utf-8"))
    data["base_scenario"] = str(
        REPOSITORY_ROOT / "examples" / "scenarios" / "uma-multicell-radio.yaml"
    )
    data["scheduler_set"] = data["scheduler_set"][:2]
    data["analysis"]["comparison_reference_scheduler"] = "round-robin"
    data["sweep_factors"] = [
        {
            "factor_id": "load",
            "json_pointer": "/traffic_profiles/broadband/source/mean_interarrival",
            "levels": [
                {"level_id": "same-a", "value": {"value": 2, "unit": "ms"}},
                {"level_id": "same-b", "value": {"value": 2000, "unit": "us"}},
            ],
        }
    ]
    path = tmp_path / "collision.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(ConfigurationValidationError, match="duplicate normalized"):
        expand_variants(load_experiment(path))


def test_type7_and_bootstrap_constant_reference() -> None:
    assert _type7_quantile([1.0, 2.0, 3.0, 4.0], 0.25) == 1.75
    registry = SemanticRngRegistry(
        "a" * 64,
        "0x11111111111111111111111111111111",
        0,
    )
    interval, record = _bootstrap_interval(
        [7.0, 7.0, 7.0],
        registry,
        "analysis/reference/constant",
        confidence_level=0.95,
        resamples=200,
    )
    assert interval == (7.0, 7.0)
    assert record is not None
    assert record.engine == "PCG64DXSM"
