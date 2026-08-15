from __future__ import annotations

import hashlib
import json
import re
import struct

import yaml
from tests.conftest import REPOSITORY_ROOT

from nr_ran_sim.config.dynamic import DynamicRadioInput
from nr_ran_sim.config.models import ScenarioConfig
from nr_ran_sim.experiments.config import ExperimentConfig

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
HTML_ASSET = re.compile(r'(?:src|href)="([^"]+)"')


def test_committed_schema_matches_typed_source() -> None:
    committed = json.loads((REPOSITORY_ROOT / "schemas" / "scenario.schema.json").read_text())
    assert committed == ScenarioConfig.model_json_schema()


def test_committed_dynamic_radio_schema_matches_typed_source() -> None:
    committed = json.loads((REPOSITORY_ROOT / "schemas" / "dynamic-radio.schema.json").read_text())
    assert committed == DynamicRadioInput.model_json_schema()


def test_committed_experiment_schema_matches_typed_source() -> None:
    committed = json.loads((REPOSITORY_ROOT / "schemas" / "experiment.schema.json").read_text())
    assert committed == ExperimentConfig.model_json_schema()


def test_all_example_scenarios_validate_against_the_typed_source() -> None:
    for scenario_path in (REPOSITORY_ROOT / "examples" / "scenarios").glob("*.yaml"):
        ScenarioConfig.model_validate(yaml.safe_load(scenario_path.read_text(encoding="utf-8")))


def test_all_example_experiments_validate_against_the_typed_source() -> None:
    for experiment_path in (REPOSITORY_ROOT / "examples" / "experiments").glob("*.yaml"):
        ExperimentConfig.model_validate(yaml.safe_load(experiment_path.read_text(encoding="utf-8")))


def test_markdown_local_links_resolve() -> None:
    broken: list[str] = []
    for document in REPOSITORY_ROOT.rglob("*.md"):
        if any(part in {".venv", "node_modules", ".vinext", "dist"} for part in document.parts):
            continue
        text = document.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#", "<")):
                continue
            relative = target.split("#", 1)[0]
            if relative and not (document.parent / relative).exists():
                broken.append(f"{document.relative_to(REPOSITORY_ROOT)} -> {target}")
        for target in HTML_ASSET.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative = target.split("#", 1)[0]
            if relative and not (document.parent / relative).exists():
                broken.append(f"{document.relative_to(REPOSITORY_ROOT)} -> {target}")
    assert broken == []


def test_social_preview_has_github_recommended_dimensions() -> None:
    preview = REPOSITORY_ROOT / "docs" / "assets" / "social-preview.png"
    with preview.open("rb") as image:
        assert image.read(8) == b"\x89PNG\r\n\x1a\n"
        length = struct.unpack(">I", image.read(4))[0]
        assert image.read(4) == b"IHDR"
        width, height = struct.unpack(">II", image.read(8))
    assert length == 13
    assert (width, height) == (1280, 640)


def test_published_evidence_manifest_matches_committed_files() -> None:
    root = REPOSITORY_ROOT / "evidence" / "scheduler-study-v1"
    manifest_path = root / "evidence-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = {record["path"]: record for record in manifest["files"]}
    committed = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }

    assert manifest["file_count"] == len(records) == len(committed)
    assert records.keys() == committed.keys()
    for relative, path in committed.items():
        payload = path.read_bytes()
        assert records[relative]["size_bytes"] == len(payload)
        assert records[relative]["file_sha256"] == hashlib.sha256(payload).hexdigest()

    plot_manifest = json.loads((root / "plots" / "plot-manifest.json").read_text())
    verification = json.loads((root / "verification.json").read_text())
    assert (
        verification["digests"]["plot_manifest_semantic_sha256"] == plot_manifest["semantic_sha256"]
    )


def test_configuration_requirements_index_has_resolvable_evidence() -> None:
    index_path = REPOSITORY_ROOT / "docs" / "verification" / "configuration-requirements-index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    requirements = index["requirements"]
    requirement_text = (
        REPOSITORY_ROOT / "docs" / "requirements" / "system-requirements.md"
    ).read_text(encoding="utf-8")
    known = set(re.findall(r"\b(?:SYS|CFG|TIME|LINK|EXP|OPS)-\d{3}\b", requirement_text))
    assert set(requirements).issubset(known)
    assert {f"CFG-{number:03d}" for number in range(1, 11)}.issubset(requirements)
    for evidence in requirements.values():
        for relative in evidence["implementation"]:
            assert (REPOSITORY_ROOT / relative).exists(), relative
        for relative in evidence["tests"]:
            if relative.endswith(".py"):
                assert (REPOSITORY_ROOT / relative).exists(), relative


def test_traffic_kernel_requirements_index_has_resolvable_evidence() -> None:
    index_path = (
        REPOSITORY_ROOT / "docs" / "verification" / "traffic-kernel-requirements-index.yaml"
    )
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    requirements = index["requirements"]
    requirement_text = (
        REPOSITORY_ROOT / "docs" / "requirements" / "system-requirements.md"
    ).read_text(encoding="utf-8")
    known = set(
        re.findall(
            r"\b(?:SYS|CFG|TIME|PROP|LINK|MAC|QOS|KPI|EXP|OPS)-\d{3}\b",
            requirement_text,
        )
    )
    assert set(requirements).issubset(known)
    assert {f"TIME-{number:03d}" for number in (1, 2, 4, 5, 6, 7, 8, 9)}.issubset(requirements)
    assert {f"QOS-{number:03d}" for number in range(1, 11)}.issubset(requirements)
    for evidence in requirements.values():
        for relative in evidence["implementation"]:
            assert (REPOSITORY_ROOT / relative).exists(), relative
        for relative in evidence["tests"]:
            if relative.endswith(".py"):
                assert (REPOSITORY_ROOT / relative).exists(), relative


def test_radio_link_requirements_index_has_resolvable_evidence() -> None:
    index_path = REPOSITORY_ROOT / "docs" / "verification" / "radio-link-requirements-index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    requirements = index["requirements"]
    requirement_text = (
        REPOSITORY_ROOT / "docs" / "requirements" / "system-requirements.md"
    ).read_text(encoding="utf-8")
    known = set(
        re.findall(
            r"\b(?:SYS|CFG|TIME|PROP|LINK|MAC|QOS|KPI|EXP|OPS)-\d{3}\b",
            requirement_text,
        )
    )
    assert set(requirements).issubset(known)
    assert {f"PROP-{number:03d}" for number in range(1, 12)}.issubset(requirements)
    assert {f"LINK-{number:03d}" for number in range(1, 7)}.issubset(requirements)
    for evidence in requirements.values():
        for relative in evidence["implementation"]:
            assert (REPOSITORY_ROOT / relative).exists(), relative
        for relative in evidence["tests"]:
            if relative.endswith(".py"):
                assert (REPOSITORY_ROOT / relative).exists(), relative


def test_nr_capacity_requirements_index_has_resolvable_evidence() -> None:
    index_path = REPOSITORY_ROOT / "docs" / "verification" / "nr-capacity-requirements-index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    requirements = index["requirements"]
    requirement_text = (
        REPOSITORY_ROOT / "docs" / "requirements" / "system-requirements.md"
    ).read_text(encoding="utf-8")
    known = set(
        re.findall(
            r"\b(?:SYS|CFG|TIME|PROP|LINK|MAC|QOS|KPI|EXP|OPS)-\d{3}\b",
            requirement_text,
        )
    )
    assert set(requirements).issubset(known)
    assert {f"LINK-{number:03d}" for number in range(7, 15)}.issubset(requirements)
    for evidence in requirements.values():
        for relative in evidence["implementation"]:
            assert (REPOSITORY_ROOT / relative).exists(), relative
        for relative in evidence["tests"]:
            if relative.endswith(".py"):
                assert (REPOSITORY_ROOT / relative).exists(), relative


def test_experiment_requirements_index_covers_every_experiment_requirement() -> None:
    index_path = REPOSITORY_ROOT / "docs" / "verification" / "experiment-requirements-index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    entries = index["entries"]
    covered = {requirement for entry in entries for requirement in entry["requirements"]}
    assert {f"EXP-{number:03d}" for number in range(1, 13)}.issubset(covered)
    for entry in entries:
        for relative in (*entry["implementation"], *entry["tests"]):
            assert (REPOSITORY_ROOT / relative).exists(), relative


def test_consolidated_matrix_covers_all_mandatory_tier_a_and_tier_b_requirements() -> None:
    matrix_path = REPOSITORY_ROOT / "docs" / "verification" / "consolidated-requirements-index.yaml"
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    system_text = (REPOSITORY_ROOT / "docs" / "requirements" / "system-requirements.md").read_text(
        encoding="utf-8"
    )
    dynamic_text = (
        REPOSITORY_ROOT / "docs" / "requirements" / "dynamic-radio-requirements.md"
    ).read_text(encoding="utf-8")
    system_ids = set(
        re.findall(
            r"^\| ((?:SYS|CFG|TIME|PROP|LINK|MAC|QOS|KPI|EXP|OPS)-\d{3}) \|", system_text, re.M
        )
    )
    dynamic_ids = set(re.findall(r"^\| (DYN-[A-Z0-9]+-\d{3}) \|", dynamic_text, re.M))
    covered: set[str] = set()
    for relative in matrix["inherited_evidence"]:
        inherited_path = REPOSITORY_ROOT / relative
        assert inherited_path.is_file(), relative
        inherited = yaml.safe_load(inherited_path.read_text(encoding="utf-8"))
        requirements = inherited.get("requirements", {})
        covered.update(requirements)
        for entry in inherited.get("entries", []):
            covered.update(entry["requirements"])
    for entry in matrix["verification_evidence"]:
        covered.update(entry["requirements"])
        for relative in (*entry["implementation"], *entry["tests"]):
            assert (REPOSITORY_ROOT / relative).exists(), relative

    assert covered.issuperset(system_ids | dynamic_ids)
    assert len(system_ids) == 110
    assert len(dynamic_ids) == 30

    deferred = {
        requirement
        for entry in matrix["deferred_boundaries"]
        for requirement in entry["requirements"]
    }
    extension_ids = set(re.findall(r"^\| (EXT-\d{3}) \|", system_text, re.M))
    assert deferred == extension_ids == {f"EXT-{number:03d}" for number in range(1, 6)}
