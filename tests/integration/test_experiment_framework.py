from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.conftest import REPOSITORY_ROOT

from nr_ran_sim.errors import ArtifactError, RunExecutionError
from nr_ran_sim.experiments.config import load_experiment
from nr_ran_sim.experiments.orchestration import execute_experiment
from nr_ran_sim.experiments.statistics import summarize_experiment
from nr_ran_sim.experiments.verification import verify_experiment_bundle
from nr_ran_sim.reporting import generate_experiment_plots
from nr_ran_sim.reporting.evidence import publish_evidence_snapshot

BASE_SCENARIO = REPOSITORY_ROOT / "examples" / "scenarios" / "uma-multicell-radio.yaml"


def _experiment_data(*, failure_policy: str = "fail-experiment") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "experiment_id": "test-paired-study",
        "description": "Small stochastic paired study for integration verification",
        "profile": "smoke",
        "base_scenario": str(BASE_SCENARIO),
        "timing": "inherit-from-scenario",
        "scheduler_set": [
            {
                "level_id": "round-robin",
                "scheduler": {"policy": "round-robin", "parameters": {}},
            },
            {
                "level_id": "proportional-fair",
                "scheduler": {
                    "policy": "proportional-fair",
                    "parameters": {
                        "averaging_alpha": 0.01,
                        "initial_rate_floor": {"value": 1, "unit": "kbit/s"},
                    },
                },
            },
        ],
        "sweep_factors": [],
        "seed_plan": {
            "master_seed": "0x12121212121212121212121212121212",
            "replication_ids": [0, 1],
            "pairing": "common-random-numbers-v1",
        },
        "analysis": {
            "confidence_level": 0.95,
            "interval_method": "percentile-bootstrap-v1",
            "bootstrap_resamples": 200,
            "comparison_reference_scheduler": "proportional-fair",
            "metrics": [
                {
                    "name": "cohort_goodput_bps",
                    "aggregation_level": "system",
                    "aggregation_id": "system",
                }
            ],
        },
        "execution": {"max_workers": 2, "failure_policy": failure_policy},
        "output": {
            "artifact_schema_version": "1.0",
            "metric_dataset_schema_version": "1.0",
            "summary_dataset_schema_version": "1.0",
            "plot_manifest_schema_version": "1.0",
        },
    }


def _write_experiment(tmp_path: Path, *, failure_policy: str = "fail-experiment") -> Path:
    path = tmp_path / f"experiment-{failure_policy}.yaml"
    path.write_text(
        yaml.safe_dump(_experiment_data(failure_policy=failure_policy), sort_keys=False),
        encoding="utf-8",
    )
    return path


def _semantic_runs(bundle: dict[str, object]) -> dict[str, str]:
    runs = bundle["runs"]
    assert isinstance(runs, list)
    return {str(item["run_id"]): str(item["run_semantic_sha256"]) for item in runs}


def test_serial_parallel_saved_results_statistics_and_plots_are_equivalent(
    tmp_path: Path,
) -> None:
    source = load_experiment(_write_experiment(tmp_path))
    serial = execute_experiment(
        source,
        tmp_path / "serial",
        code_revision="a" * 40,
        working_tree_dirty=False,
        max_workers=1,
    )
    parallel = execute_experiment(
        source,
        tmp_path / "parallel",
        code_revision="a" * 40,
        working_tree_dirty=False,
        max_workers=2,
    )
    assert serial["completeness"] == parallel["completeness"]
    assert _semantic_runs(serial) == _semantic_runs(parallel)
    assert (
        serial["metric_dataset"]["semantic_sha256"] == parallel["metric_dataset"]["semantic_sha256"]
    )

    run_records = serial["runs"]
    assert isinstance(run_records, list)
    exogenous_by_replication: dict[int, set[str]] = {}
    for run in run_records:
        exogenous_by_replication.setdefault(run["replication_id"], set()).add(
            run["exogenous_configuration_sha256"]
        )
    assert all(len(values) == 1 for values in exogenous_by_replication.values())

    serial_summary = summarize_experiment(tmp_path / "serial")
    parallel_summary = summarize_experiment(tmp_path / "parallel")
    assert serial_summary["semantic_sha256"] == parallel_summary["semantic_sha256"]
    comparisons = serial_summary["paired_comparisons"]
    assert isinstance(comparisons, list)
    assert comparisons[0]["n_valid_pairs"] == 2
    plots = generate_experiment_plots(tmp_path / "serial")
    assert plots["plot_count"] == 1
    plotted = plots["plots"][0]["plotted_points"]
    assert all(point["source_row_ids"] for point in plotted)
    plot_svg = (tmp_path / "serial" / "plots" / plots["plots"][0]["path"]).read_text(
        encoding="utf-8"
    )
    assert 'data-design-system="systems-lab-v1"' in plot_svg
    assert "#f4f6f8" in plot_svg
    assert "Arial Narrow" in plot_svg
    assert "<linearGradient" not in plot_svg
    verification = verify_experiment_bundle(tmp_path / "serial")
    assert verification["status"] == "pass"
    assert verification["counts"] == {
        "runs": 4,
        "replication_rows": 4,
        "estimates": 2,
        "paired_comparisons": 1,
        "plots": 1,
        "pairing_groups": 2,
    }
    evidence = publish_evidence_snapshot(tmp_path / "serial", tmp_path / "evidence")
    assert evidence["file_count"] == 6
    assert (tmp_path / "evidence" / "verification.json").is_file()
    assert (tmp_path / "evidence" / "metrics" / "summary.json").is_file()
    with pytest.raises(ArtifactError, match="already exists"):
        publish_evidence_snapshot(tmp_path / "serial", tmp_path / "evidence")

    with pytest.raises(ArtifactError, match="already exists"):
        execute_experiment(
            source,
            tmp_path / "serial",
            code_revision="a" * 40,
            working_tree_dirty=False,
        )


def test_serial_execution_writes_each_result_before_starting_the_next_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nr_ran_sim.experiments import orchestration

    original_run = orchestration.run_system_simulation
    original_write = orchestration.SimulationResult.write
    events: list[tuple[str, str]] = []

    def recording_run(*args: object, **kwargs: object) -> object:
        result = original_run(*args, **kwargs)
        events.append(("run", str(result.identity.id)))
        return result

    def recording_write(
        result: orchestration.SimulationResult,
        path: Path,
        *,
        force: bool = False,
    ) -> None:
        events.append(("write", str(result.identity.id)))
        original_write(result, path, force=force)

    monkeypatch.setattr(orchestration, "run_system_simulation", recording_run)
    monkeypatch.setattr(orchestration.SimulationResult, "write", recording_write)
    source = load_experiment(_write_experiment(tmp_path))
    execute_experiment(
        source,
        tmp_path / "streamed",
        code_revision="d" * 40,
        working_tree_dirty=False,
        max_workers=1,
    )

    assert [kind for kind, _ in events] == ["run", "write"] * 4
    assert all(events[index][1] == events[index + 1][1] for index in range(0, 8, 2))


def test_failed_replication_is_retained_and_blocks_default_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nr_ran_sim.experiments import orchestration

    original = orchestration.run_system_simulation

    def fail_round_robin(*args: object, **kwargs: object) -> object:
        scenario = args[0]
        if scenario.scheduler.policy == "round-robin":
            raise RunExecutionError("injected failure", {"test": True})
        return original(*args, **kwargs)

    monkeypatch.setattr(orchestration, "run_system_simulation", fail_round_robin)
    source = load_experiment(_write_experiment(tmp_path, failure_policy="retain-and-exclude"))
    bundle = execute_experiment(
        source,
        tmp_path / "partial",
        code_revision="b" * 40,
        working_tree_dirty=True,
        max_workers=1,
    )
    assert bundle["completeness"]["status"] == "partial"
    assert bundle["completeness"]["failed_runs"] == 2
    failures = bundle["failed_replications"]
    assert isinstance(failures, list)
    assert {item["error"]["code"] for item in failures} == {"run_execution_error"}
    with pytest.raises(RunExecutionError, match="incomplete"):
        summarize_experiment(tmp_path / "partial")
    summary = summarize_experiment(tmp_path / "partial", allow_partial=True)
    assert summary["partial_input"] is True


def test_tampered_metric_dataset_is_rejected(tmp_path: Path) -> None:
    source = load_experiment(_write_experiment(tmp_path))
    execute_experiment(
        source,
        tmp_path / "tampered",
        code_revision="c" * 40,
        working_tree_dirty=False,
        max_workers=1,
    )
    metric_path = tmp_path / "tampered" / "metrics" / "replications.json"
    payload = json.loads(metric_path.read_text(encoding="utf-8"))
    payload["rows"][0]["value"] = 123456789
    metric_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ArtifactError, match="checksum"):
        summarize_experiment(tmp_path / "tampered")


def test_tampered_saved_plot_is_rejected_by_bundle_verification(tmp_path: Path) -> None:
    source = load_experiment(_write_experiment(tmp_path))
    target = tmp_path / "plot-tampered"
    execute_experiment(
        source,
        target,
        code_revision="e" * 40,
        working_tree_dirty=False,
        max_workers=2,
    )
    summarize_experiment(target)
    plot_manifest = generate_experiment_plots(target)
    plots = plot_manifest["plots"]
    assert isinstance(plots, list)
    plot_path = target / "plots" / plots[0]["path"]
    plot_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ArtifactError, match="digest mismatch"):
        verify_experiment_bundle(target)
