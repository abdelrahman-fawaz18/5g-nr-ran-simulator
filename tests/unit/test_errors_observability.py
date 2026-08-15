from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest

import nr_ran_sim.metadata as metadata_module
from nr_ran_sim.errors import ConfigurationValidationError
from nr_ran_sim.metadata import environment_metadata
from nr_ran_sim.observability import JsonFormatter, configure_logging, log_event


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_project_error_has_stable_machine_representation() -> None:
    error = ConfigurationValidationError("bad input", {"field": "radio"})
    assert str(error) == "bad input"
    assert error.exit_code == 2
    assert error.as_dict() == {
        "error": "configuration_validation_error",
        "message": "bad input",
        "context": {"field": "radio"},
    }


def test_json_formatter_and_structured_context() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "validated", (), None)
    record.context = {"scenario": "example"}
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "info"
    assert payload["event"] == "validated"
    assert payload["context"] == {"scenario": "example"}


def test_configured_logger_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    log_event(logging.getLogger("test"), logging.INFO, "ready", count=1)
    captured = json.loads(capsys.readouterr().err)
    assert captured["event"] == "ready"
    assert captured["context"] == {"count": 1}


def test_environment_metadata_is_diagnostic_not_scenario_identity() -> None:
    metadata = environment_metadata()
    assert metadata["simulator_version"] == "0.1.0"
    assert metadata["python_implementation"] == "CPython"
    assert metadata["dependencies"]["pydantic"]
    assert "platform" in metadata


def test_dependency_metadata_is_resolved_once_and_returned_as_a_fresh_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def version(name: str) -> str:
        calls.append(name)
        return f"test-{name}"

    metadata_module._dependency_versions.cache_clear()
    monkeypatch.setattr(metadata_module.importlib.metadata, "version", version)
    first = environment_metadata()
    first["dependencies"]["numpy"] = "mutated"
    second = environment_metadata()

    assert calls == list(metadata_module.RUNTIME_DEPENDENCIES)
    assert second["dependencies"]["numpy"] == "test-numpy"
    metadata_module._dependency_versions.cache_clear()
