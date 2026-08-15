from __future__ import annotations

import json
from pathlib import Path

import pytest

from nr_ran_sim.config import load_scenario, normalize_scenario
from nr_ran_sim.errors import ArtifactError
from nr_ran_sim.radio.capacity_snapshot import FULL_ALLOCATION_CONTEXT, build_capacity_snapshot
from nr_ran_sim.radio.snapshot import build_radio_snapshot

MASTER_SEED = "0x11111111111111111111111111111111"
ROOT = Path(__file__).parents[2]
SCENARIO = ROOT / "examples" / "scenarios" / "uma-multicell-radio.yaml"


def test_capacity_snapshot_is_deterministic_traceable_and_visualization_ready() -> None:
    scenario = normalize_scenario(load_scenario(SCENARIO))
    first = build_capacity_snapshot(scenario, master_seed=MASTER_SEED, replication_id=0)
    replay = build_capacity_snapshot(scenario, master_seed=MASTER_SEED, replication_id=0)
    radio = build_radio_snapshot(scenario, master_seed=MASTER_SEED, replication_id=0)

    assert first.to_json() == replay.to_json()
    assert first.semantic_sha256 == replay.semantic_sha256
    assert first.radio_snapshot_sha256 == radio.semantic_sha256
    assert first.configuration_sha256 == radio.configuration_sha256
    assert first.schema_version == "1.0"
    assert first.resource_grid.prb_count == 273
    assert first.resource_grid.tbs_data_re_per_prb == 144
    assert len(first.observations) == 12
    assert [item.ue_id for item in first.observations] == sorted(
        item.ue_id for item in first.observations
    )
    assert all(item.allocation_context == FULL_ALLOCATION_CONTEXT for item in first.observations)
    assert all(item.capacity.allocated_prbs == 273 for item in first.observations)
    assert all(item.capacity.state == "capacity_available" for item in first.observations)
    assert len({item.capacity.capacity_bit_rate_bps for item in first.observations}) > 1

    payload = json.loads(first.to_json())
    assert payload["semantic_sha256"] == first.semantic_sha256
    assert payload["radio_snapshot_sha256"] == radio.semantic_sha256
    assert "not simultaneous" in payload["interpretation"]
    assert payload["model_profiles"]["link_adaptation"] == "analytical-awgn-gap-v1"


def test_capacity_snapshot_changes_with_radio_realization() -> None:
    scenario = normalize_scenario(load_scenario(SCENARIO))
    first = build_capacity_snapshot(scenario, master_seed=MASTER_SEED, replication_id=0)
    changed = build_capacity_snapshot(
        scenario,
        master_seed="0x22222222222222222222222222222222",
        replication_id=0,
    )
    assert first.semantic_sha256 != changed.semantic_sha256
    assert first.radio_snapshot_sha256 != changed.radio_snapshot_sha256


def test_capacity_snapshot_write_is_atomic_and_collision_safe(tmp_path: Path) -> None:
    scenario = normalize_scenario(load_scenario(SCENARIO))
    snapshot = build_capacity_snapshot(scenario, master_seed=MASTER_SEED, replication_id=0)
    target = tmp_path / "nested" / "capacity.json"
    snapshot.write(target)
    assert json.loads(target.read_text(encoding="utf-8"))["semantic_sha256"] == (
        snapshot.semantic_sha256
    )
    with pytest.raises(ArtifactError, match="already exists"):
        snapshot.write(target)
    snapshot.write(target, force=True)
