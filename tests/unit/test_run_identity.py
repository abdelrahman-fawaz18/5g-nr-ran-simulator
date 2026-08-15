from __future__ import annotations

import pytest

from nr_ran_sim.errors import ConfigurationValidationError
from nr_ran_sim.experiments import (
    SemanticRngRegistry,
    build_run_identity,
    build_run_metadata,
)

MASTER = "0x0123456789abcdeffedcba9876543210"


def test_run_identity_is_content_derived_and_mapping_order_independent() -> None:
    common = {
        "configuration_sha256": "a" * 64,
        "master_seed": MASTER,
        "replication_id": 4,
        "code_revision": "b" * 40,
    }
    first = build_run_identity(
        **common,
        model_profiles={"propagation": "p1", "fidelity": "f1"},
        experiment_factors={"load": "medium", "scheduler": "rr"},
    )
    replay = build_run_identity(
        **common,
        model_profiles={"fidelity": "f1", "propagation": "p1"},
        experiment_factors={"scheduler": "rr", "load": "medium"},
    )
    changed = build_run_identity(
        **common,
        model_profiles={"fidelity": "f1", "propagation": "p1"},
        experiment_factors={"scheduler": "pf", "load": "medium"},
    )

    assert first == replay
    assert first.id != changed.id
    assert str(first.id).startswith("run/")
    assert len(str(first.id).split("/", 1)[1]) == 64


def test_run_metadata_separates_environment_and_sorted_rng_manifest() -> None:
    identity = build_run_identity(
        configuration_sha256="a" * 64,
        master_seed=MASTER,
        replication_id=0,
        code_revision="b" * 40,
        model_profiles={"fidelity": "f1"},
    )
    registry = SemanticRngRegistry("a" * 64, MASTER, 0)
    registry.acquire("traffic/z/interarrival", owner="z")
    registry.acquire("traffic/a/interarrival", owner="a")

    metadata = build_run_metadata(
        identity,
        working_tree_dirty=True,
        rng_streams=registry.manifest(),
    )

    payload = metadata.as_dict()
    assert payload["working_tree_dirty"] is True
    assert payload["identity"] == identity.as_dict()
    assert payload["environment"]["dependencies"]["numpy"]
    assert [record["semantic_path"] for record in payload["rng_streams"]] == [
        "traffic/a/interarrival",
        "traffic/z/interarrival",
    ]


@pytest.mark.parametrize(
    "replacement",
    [
        {"configuration_sha256": "bad"},
        {"master_seed": "bad"},
        {"replication_id": -1},
        {"code_revision": "not-a-git-id"},
        {"model_profiles": {}},
    ],
)
def test_run_identity_inputs_fail_closed(replacement: dict[str, object]) -> None:
    parameters: dict[str, object] = {
        "configuration_sha256": "a" * 64,
        "master_seed": MASTER,
        "replication_id": 0,
        "code_revision": "b" * 40,
        "model_profiles": {"fidelity": "f1"},
    }
    parameters.update(replacement)
    with pytest.raises(ConfigurationValidationError):
        build_run_identity(**parameters)  # type: ignore[arg-type]
