"""Safe YAML/JSON loading with stable project exceptions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from nr_ran_sim.config.models import ScenarioConfig
from nr_ran_sim.errors import ConfigurationFileError, ConfigurationValidationError

SUPPORTED_SUFFIXES = frozenset({".json", ".yaml", ".yml"})


def load_scenario(path: Path) -> ScenarioConfig:
    """Read and structurally validate one scenario document."""

    resolved = path.resolve()
    if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ConfigurationFileError(
            "scenario file must use .json, .yaml, or .yml",
            {"path": str(path), "suffix": resolved.suffix},
        )
    try:
        source = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationFileError(
            "unable to read scenario file",
            {"path": str(path), "detail": str(exc)},
        ) from exc
    try:
        raw = _decode(source, resolved.suffix.lower())
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigurationFileError(
            "scenario document is not valid YAML/JSON",
            {"path": str(path), "detail": str(exc)},
        ) from exc
    if not isinstance(raw, dict):
        raise ConfigurationValidationError(
            "scenario document root must be an object",
            {"path": str(path), "received_type": type(raw).__name__},
        )
    try:
        return ScenarioConfig.model_validate(raw)
    except ValidationError as exc:
        issues = [
            {
                "field": ".".join(str(part) for part in issue["loc"]),
                "message": issue["msg"],
                "type": issue["type"],
                "received": _safe_input(issue.get("input")),
            }
            for issue in exc.errors(include_url=False)
        ]
        raise ConfigurationValidationError(
            f"scenario validation failed with {len(issues)} issue(s)",
            {"path": str(path), "issues": issues},
        ) from exc


def _decode(source: str, suffix: str) -> Any:
    if suffix == ".json":
        return json.loads(source)
    return yaml.safe_load(source)


def _safe_input(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return f"list[{len(value)}]"
    if isinstance(value, dict):
        return f"object[{len(value)}]"
    return type(value).__name__
