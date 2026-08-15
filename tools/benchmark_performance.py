"""Run the versioned runtime and Python-managed-memory benchmark suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import tracemalloc
from pathlib import Path
from typing import Any

import yaml

from nr_ran_sim.config import load_scenario, normalize_scenario
from nr_ran_sim.experiments.dynamic_simulation import run_dynamic_system_simulation
from nr_ran_sim.experiments.simulation import run_system_simulation
from nr_ran_sim.metadata import environment_metadata

ROOT = Path(__file__).parents[1]
DEFAULT_SUITE = ROOT / "benchmarks" / "performance-workloads.yaml"
MIB = 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.repeat <= 0:
        parser.error("--repeat must be positive")

    report = run_suite(args.suite.resolve(), repeat=args.repeat)
    payload = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        _write_report(args.output.resolve(), payload, force=args.force)
    print(payload, end="")
    return 0 if report["passed"] else 2


def run_suite(suite_path: Path, *, repeat: int) -> dict[str, Any]:
    suite_bytes = suite_path.read_bytes()
    suite = yaml.safe_load(suite_bytes)
    root = _repository_root(suite_path)
    results = [_run_workload(root, suite, workload, repeat) for workload in suite["workloads"]]
    return {
        "schema_version": "1.0",
        "suite_id": suite["suite_id"],
        "suite_sha256": hashlib.sha256(suite_bytes).hexdigest(),
        "methodology": suite["methodology"],
        "repeat_count": repeat,
        "runtime_statistic": "median perf_counter wall seconds after one warm-up",
        "memory_statistic": "maximum tracemalloc Python-managed peak bytes",
        "memory_limitation": "native allocations outside Python's allocator are excluded",
        "environment": environment_metadata(),
        "workloads": results,
        "passed": all(result["passed"] for result in results),
    }


def _run_workload(
    root: Path,
    suite: dict[str, Any],
    workload: dict[str, Any],
    repeat: int,
) -> dict[str, Any]:
    scenario = normalize_scenario(load_scenario(root / workload["scenario"]))
    dynamic = workload["runner"] == "dynamic"
    runner = run_dynamic_system_simulation if dynamic else run_system_simulation
    run_arguments = {
        "master_seed": suite["master_seed"],
        "replication_id": suite["replication_id"],
        "code_revision": suite["code_revision"],
        "working_tree_dirty": False,
    }
    warmup = runner(scenario, **run_arguments)
    elapsed_seconds: list[float] = []
    peak_bytes: list[int] = []
    semantic_digests = [warmup.semantic_sha256]
    for _ in range(repeat):
        tracemalloc.start()
        start = time.perf_counter_ns()
        result = runner(scenario, **run_arguments)
        elapsed_seconds.append((time.perf_counter_ns() - start) / 1_000_000_000)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_bytes.append(peak)
        semantic_digests.append(result.semantic_sha256)

    ue_count = sum(group.count for group in scenario.topology.ue_groups.values())
    if ue_count != workload["expected_ue_count"]:
        raise ValueError(f"{workload['id']} UE count changed from its approved workload contract")
    median_seconds = statistics.median(elapsed_seconds)
    maximum_peak_bytes = max(peak_bytes)
    runtime_passed = median_seconds <= workload["runtime_budget_seconds"]
    memory_passed = maximum_peak_bytes <= workload["python_peak_memory_budget_mib"] * MIB
    replay_passed = len(set(semantic_digests)) == 1
    return {
        "id": workload["id"],
        "scenario": workload["scenario"],
        "runner": workload["runner"],
        "ue_count": ue_count,
        "scheduling_interval_count": len(result.intervals),
        "elapsed_seconds": elapsed_seconds,
        "median_elapsed_seconds": median_seconds,
        "runtime_budget_seconds": workload["runtime_budget_seconds"],
        "peak_python_bytes": peak_bytes,
        "maximum_peak_python_mib": maximum_peak_bytes / MIB,
        "python_peak_memory_budget_mib": workload["python_peak_memory_budget_mib"],
        "semantic_sha256": result.semantic_sha256,
        "semantic_replay_passed": replay_passed,
        "runtime_budget_passed": runtime_passed,
        "memory_budget_passed": memory_passed,
        "passed": runtime_passed and memory_passed and replay_passed,
    }


def _repository_root(suite_path: Path) -> Path:
    candidate = suite_path.parent.parent
    if not (candidate / "pyproject.toml").is_file():
        raise ValueError("benchmark suite must be stored under the repository benchmarks directory")
    return candidate


def _write_report(path: Path, payload: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"benchmark report already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
