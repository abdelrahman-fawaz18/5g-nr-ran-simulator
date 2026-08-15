from __future__ import annotations

import subprocess
import sys

from tests.conftest import REPOSITORY_ROOT

SCENARIO = REPOSITORY_ROOT / "examples" / "scenarios" / "uma-multicell-radio.yaml"
EXPECTED_SEMANTIC_SHA256 = "0238da147cff69146437842c3b151537a732f9b786b3deadf3520e0e655658a6"
REPLAY_PROGRAM = """
from pathlib import Path
import sys
from nr_ran_sim.config import load_scenario, normalize_scenario
from nr_ran_sim.radio.capacity_snapshot import build_capacity_snapshot

scenario = normalize_scenario(load_scenario(Path(sys.argv[1])))
snapshot = build_capacity_snapshot(
    scenario,
    master_seed="0x11111111111111111111111111111111",
    replication_id=0,
)
print(snapshot.semantic_sha256)
"""


def _execute_in_fresh_process() -> str:
    completed = subprocess.run(
        [sys.executable, "-c", REPLAY_PROGRAM, str(SCENARIO)],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_capacity_snapshot_replays_across_fresh_processes() -> None:
    assert _execute_in_fresh_process() == _execute_in_fresh_process() == EXPECTED_SEMANTIC_SHA256
