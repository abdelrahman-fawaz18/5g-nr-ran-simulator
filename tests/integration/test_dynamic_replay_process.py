from __future__ import annotations

import subprocess
import sys

from tests.conftest import REPOSITORY_ROOT

SCENARIO = REPOSITORY_ROOT / "examples" / "scenarios" / "dynamic-fr1-mobility.yaml"
REPLAY_PROGRAM = """
from pathlib import Path
import sys
from nr_ran_sim.config import load_scenario, normalize_scenario
from nr_ran_sim.experiments.dynamic_simulation import run_dynamic_system_simulation

scenario = normalize_scenario(load_scenario(Path(sys.argv[1])))
result = run_dynamic_system_simulation(
    scenario,
    master_seed="0x44444444444444444444444444444444",
    replication_id=1,
    code_revision="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    working_tree_dirty=False,
)
print(result.semantic_sha256)
"""
EXPECTED_SEMANTIC_SHA256 = "7da14bdd9275d1b5d50228abd29171b45fc7f31ac341e107242c992407951f00"


def _execute_in_fresh_process() -> str:
    completed = subprocess.run(
        [sys.executable, "-c", REPLAY_PROGRAM, str(SCENARIO)],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_dynamic_run_replays_across_fresh_processes() -> None:
    assert _execute_in_fresh_process() == _execute_in_fresh_process() == EXPECTED_SEMANTIC_SHA256
