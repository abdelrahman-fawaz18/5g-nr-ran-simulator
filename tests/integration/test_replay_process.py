from __future__ import annotations

import subprocess
import sys

from tests.conftest import REPOSITORY_ROOT, TRAFFIC_SCENARIO

REPLAY_PROGRAM = """
from pathlib import Path
import sys
from nr_ran_sim.config import build_manifest, load_scenario, normalize_scenario
from nr_ran_sim.traffic import run_traffic_mechanics

scenario = normalize_scenario(load_scenario(Path(sys.argv[1])))
manifest = build_manifest(scenario)
result = run_traffic_mechanics(
    scenario,
    configuration_sha256=manifest.configuration_sha256,
    master_seed="0x0123456789abcdeffedcba9876543210",
    replication_id=11,
    code_revision="cccccccccccccccccccccccccccccccccccccccc",
    working_tree_dirty=False,
)
print(result.semantic_sha256)
"""
EXPECTED_SEMANTIC_SHA256 = "51f533e59ec6adf8219cd20f384664580817b3643bdf15c2e4e037eb298e38d4"


def _execute_in_fresh_process() -> str:
    completed = subprocess.run(
        [sys.executable, "-c", REPLAY_PROGRAM, str(TRAFFIC_SCENARIO)],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_semantic_replay_is_identical_across_fresh_processes() -> None:
    assert _execute_in_fresh_process() == _execute_in_fresh_process() == EXPECTED_SEMANTIC_SHA256
