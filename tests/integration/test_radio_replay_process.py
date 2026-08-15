from __future__ import annotations

import subprocess
import sys

from tests.conftest import REPOSITORY_ROOT

SCENARIO = REPOSITORY_ROOT / "examples" / "scenarios" / "uma-multicell-radio.yaml"
EXPECTED_SEMANTIC_SHA256 = "81393036061cf09803af753367cb0c24957684c0f8d505012b5ea68487340e37"
REPLAY_PROGRAM = """
from pathlib import Path
import sys
from nr_ran_sim.config import load_scenario, normalize_scenario
from nr_ran_sim.radio.snapshot import build_radio_snapshot

scenario = normalize_scenario(load_scenario(Path(sys.argv[1])))
snapshot = build_radio_snapshot(
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


def test_radio_snapshot_replays_across_fresh_processes() -> None:
    assert _execute_in_fresh_process() == _execute_in_fresh_process() == EXPECTED_SEMANTIC_SHA256
