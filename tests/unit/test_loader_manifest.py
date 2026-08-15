from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from nr_ran_sim.config.loader import load_scenario
from nr_ran_sim.config.manifest import build_manifest
from nr_ran_sim.config.normalize import normalize_scenario
from nr_ran_sim.errors import ArtifactError, ConfigurationFileError, ConfigurationValidationError


def _write_yaml(path: Path, data: Any) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_yaml_and_json_load_to_same_manifest(
    tmp_path: Path,
    scenario_data: dict[str, Any],
) -> None:
    yaml_path = _write_yaml(tmp_path / "scenario.yaml", scenario_data)
    json_path = tmp_path / "scenario.json"
    json_path.write_text(json.dumps(scenario_data), encoding="utf-8")
    yaml_manifest = build_manifest(normalize_scenario(load_scenario(yaml_path)))
    json_manifest = build_manifest(normalize_scenario(load_scenario(json_path)))
    assert yaml_manifest.configuration_sha256 == json_manifest.configuration_sha256
    assert yaml_manifest.to_json() == json_manifest.to_json()


@pytest.mark.parametrize("suffix", [".txt", ".toml"])
def test_loader_rejects_unsupported_suffix(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"scenario{suffix}"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigurationFileError, match="must use"):
        load_scenario(path)


def test_loader_reports_missing_and_malformed_files(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationFileError, match="unable to read"):
        load_scenario(tmp_path / "missing.yaml")
    malformed = tmp_path / "bad.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ConfigurationFileError, match="not valid"):
        load_scenario(malformed)


def test_loader_rejects_non_object_and_surfaces_fields(tmp_path: Path) -> None:
    root_list = _write_yaml(tmp_path / "list.yaml", [1, 2])
    with pytest.raises(ConfigurationValidationError, match="root must be an object"):
        load_scenario(root_list)

    invalid = _write_yaml(tmp_path / "invalid.yaml", {"schema_version": "1.0"})
    with pytest.raises(ConfigurationValidationError) as raised:
        load_scenario(invalid)
    issues = raised.value.context["issues"]
    assert isinstance(issues, list)
    assert any(issue["field"] == "scenario_id" for issue in issues)


def test_manifest_write_is_atomic_and_collision_safe(
    tmp_path: Path,
    scenario_data: dict[str, Any],
) -> None:
    scenario = load_scenario(_write_yaml(tmp_path / "scenario.yaml", scenario_data))
    manifest = build_manifest(normalize_scenario(scenario))
    output = tmp_path / "nested" / "manifest.json"
    manifest.write(output)
    assert output.read_text(encoding="utf-8") == manifest.to_json()
    with pytest.raises(ArtifactError, match="already exists"):
        manifest.write(output)
    manifest.write(output, force=True)
    assert not (output.parent / ".manifest.json.tmp").exists()


def test_manifest_is_stable_under_mapping_declaration_order(
    tmp_path: Path,
    scenario_data: dict[str, Any],
) -> None:
    original = build_manifest(
        normalize_scenario(load_scenario(_write_yaml(tmp_path / "a.yaml", scenario_data)))
    )
    reversed_data = dict(reversed(list(scenario_data.items())))
    reordered = build_manifest(
        normalize_scenario(load_scenario(_write_yaml(tmp_path / "b.yaml", reversed_data)))
    )
    assert original.configuration_sha256 == reordered.configuration_sha256
    assert original.configuration_sha256 == (
        "de1a508d319fb0d578a8b9d255cc978291a1beba89bbe68e4fc755c4280ca2c6"
    )
    assert len(original.configuration_sha256) == 64
