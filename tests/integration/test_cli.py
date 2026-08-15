from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.conftest import EXAMPLE_SCENARIO

from nr_ran_sim.cli.main import run

MASTER_SEED = "0x00000000000000000000000000000001"
SCHEDULER_SCENARIO = EXAMPLE_SCENARIO.parents[0] / "scheduler-qos-smoke.yaml"


def test_validate_cli_emits_and_writes_identical_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "manifest.json"
    assert run(["validate", str(EXAMPLE_SCENARIO), "--output", str(output)]) == 0
    captured = capsys.readouterr()
    assert captured.out == output.read_text(encoding="utf-8")
    payload = json.loads(captured.out)
    assert payload["normalized"]["radio"]["prb_count"] == 273


def test_validate_cli_quiet_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "manifest.json"
    assert run(["validate", str(EXAMPLE_SCENARIO), "--output", str(output), "--quiet"]) == 0
    assert capsys.readouterr().out == ""
    assert output.exists()


def test_cli_renders_expected_error_as_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("schema_version: '1.0'\n", encoding="utf-8")
    assert run(["--error-format", "json", "validate", str(invalid)]) == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.err.splitlines()[-1])
    assert payload["error"] == "configuration_validation_error"


def test_cli_schema_and_environment_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    schema = tmp_path / "schema.json"
    assert run(["schema", "--output", str(schema)]) == 0
    assert json.loads(schema.read_text(encoding="utf-8"))["title"] == "ScenarioConfig"
    dynamic_schema = tmp_path / "dynamic-schema.json"
    assert run(["dynamic-schema", "--output", str(dynamic_schema)]) == 0
    assert json.loads(dynamic_schema.read_text(encoding="utf-8"))["title"] == "DynamicRadioInput"
    experiment_schema = tmp_path / "experiment-schema.json"
    assert run(["experiment-schema", "--output", str(experiment_schema)]) == 0
    assert json.loads(experiment_schema.read_text(encoding="utf-8"))["title"] == "ExperimentConfig"
    assert run(["environment"]) == 0
    assert "simulator_version" in json.loads(capsys.readouterr().out)


def test_cli_refuses_schema_collision(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text("existing", encoding="utf-8")
    assert run(["schema", "--output", str(schema)]) == 3
    assert "already exists" in capsys.readouterr().err


def test_radio_snapshot_cli_emits_and_writes_identical_scene(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "radio.json"
    assert (
        run(
            [
                "radio-snapshot",
                str(EXAMPLE_SCENARIO),
                "--master-seed",
                MASTER_SEED,
                "--replication-id",
                "0",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.out == output.read_text(encoding="utf-8")
    payload = json.loads(captured.out)
    assert payload["schema_version"] == "1.0"
    assert len(payload["links"]) == 20


def test_radio_snapshot_cli_quiet_and_collision_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "radio.json"
    command = [
        "radio-snapshot",
        str(EXAMPLE_SCENARIO),
        "--master-seed",
        MASTER_SEED,
        "--replication-id",
        "0",
        "--output",
        str(output),
        "--quiet",
    ]
    assert run(command) == 0
    assert capsys.readouterr().out == ""
    assert run(command) == 3
    assert "already exists" in capsys.readouterr().err


def test_capacity_snapshot_cli_emits_and_writes_identical_diagnostics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "capacity.json"
    command = [
        "capacity-snapshot",
        str(EXAMPLE_SCENARIO),
        "--master-seed",
        MASTER_SEED,
        "--replication-id",
        "0",
        "--output",
        str(output),
    ]
    assert run(command) == 0
    captured = capsys.readouterr()
    assert captured.out == output.read_text(encoding="utf-8")
    payload = json.loads(captured.out)
    assert payload["schema_version"] == "1.0"
    assert len(payload["observations"]) == 20
    assert payload["resource_grid"]["prb_count"] == 273

    command.append("--quiet")
    assert run(command) == 3
    assert "already exists" in capsys.readouterr().err
    command.append("--force")
    assert run(command) == 0
    assert capsys.readouterr().out == ""


def test_simulate_cli_emits_versioned_scheduler_and_kpi_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "simulation.json"
    command = [
        "simulate",
        str(SCHEDULER_SCENARIO),
        "--master-seed",
        MASTER_SEED,
        "--replication-id",
        "0",
        "--code-revision",
        "a" * 40,
        "--working-tree-state",
        "clean",
        "--output",
        str(output),
    ]
    assert run(command) == 0
    captured = capsys.readouterr()
    assert captured.out == output.read_text(encoding="utf-8")
    payload = json.loads(captured.out)
    assert payload["schema_version"] == "1.0"
    assert payload["scheduler_policy_id"] == "proportional-fair-v1"
    assert len(payload["intervals"]) == 12
    assert payload["kpis"]["definition_version"] == "1.0"

    command.extend(("--quiet", "--force"))
    assert run(command) == 0
    assert capsys.readouterr().out == ""
