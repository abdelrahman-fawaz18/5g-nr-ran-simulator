from __future__ import annotations

import importlib.util
from types import ModuleType

import pytest

from tests.conftest import REPOSITORY_ROOT


def _benchmark_module() -> ModuleType:
    path = REPOSITORY_ROOT / "tools" / "benchmark_performance.py"
    specification = importlib.util.spec_from_file_location("performance_benchmark", path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.mark.performance
def test_representative_performance_suite_meets_budgets_and_replays() -> None:
    module = _benchmark_module()
    report = module.run_suite(
        REPOSITORY_ROOT / "benchmarks" / "performance-workloads.yaml",
        repeat=1,
    )

    assert report["passed"] is True
    assert report["repeat_count"] == 1
    assert len(report["workloads"]) == 4
    assert all(workload["semantic_replay_passed"] for workload in report["workloads"])
    assert all(workload["runtime_budget_passed"] for workload in report["workloads"])
    assert all(workload["memory_budget_passed"] for workload in report["workloads"])
