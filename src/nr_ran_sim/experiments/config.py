"""Strict experiment authoring and deterministic design expansion."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from nr_ran_sim.config import ScenarioConfig, build_manifest, load_scenario, normalize_scenario
from nr_ran_sim.config.manifest import canonical_json_bytes
from nr_ran_sim.config.models import Identifier, SchedulerConfig
from nr_ran_sim.config.normalize import NormalizedScenario
from nr_ran_sim.errors import ConfigurationFileError, ConfigurationValidationError
from nr_ran_sim.experiments.seeds import MASTER_SEED

EXPERIMENT_SCHEMA_VERSION = "1.0"
EXPERIMENT_ARTIFACT_SCHEMA_VERSION = "1.0"
METRIC_DATASET_SCHEMA_VERSION = "1.0"
SUMMARY_DATASET_SCHEMA_VERSION = "1.0"
PLOT_MANIFEST_SCHEMA_VERSION = "1.0"
_JSON_POINTER = re.compile(r"^(?:/(?:[^~/]|~[01])*)+$")


class _FrozenStrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class SchedulerLevel(_FrozenStrictModel):
    level_id: Identifier
    scheduler: SchedulerConfig


class FactorLevel(_FrozenStrictModel):
    level_id: Identifier
    value: JsonValue


class SweepFactor(_FrozenStrictModel):
    factor_id: Identifier
    json_pointer: str = Field(min_length=2, max_length=300)
    levels: tuple[FactorLevel, ...] = Field(min_length=2)

    @field_validator("json_pointer")
    @classmethod
    def valid_pointer(cls, value: str) -> str:
        if not _JSON_POINTER.fullmatch(value):
            raise ValueError("json_pointer must be an RFC 6901 absolute pointer")
        if value in {"/schema_version", "/scenario_id", "/description", "/scheduler"}:
            raise ValueError("identity/label/scheduler fields are not valid generic sweep targets")
        return value

    @model_validator(mode="after")
    def unique_levels(self) -> SweepFactor:
        ids = [item.level_id for item in self.levels]
        if len(ids) != len(set(ids)):
            raise ValueError(f"factor {self.factor_id!r} contains duplicate level IDs")
        return self


class SeedPlan(_FrozenStrictModel):
    master_seed: str
    replication_ids: tuple[int, ...] = Field(min_length=2)
    pairing: Literal["common-random-numbers-v1"] = "common-random-numbers-v1"

    @field_validator("master_seed")
    @classmethod
    def valid_master_seed(cls, value: str) -> str:
        if not MASTER_SEED.fullmatch(value):
            raise ValueError("master_seed must be a 128-bit hexadecimal string prefixed by 0x")
        return value.lower()

    @field_validator("replication_ids")
    @classmethod
    def valid_replications(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(item < 0 for item in value):
            raise ValueError("replication IDs must be nonnegative")
        if len(value) != len(set(value)):
            raise ValueError("replication IDs must be unique")
        return tuple(sorted(value))


class MetricSelector(_FrozenStrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    aggregation_level: Literal["bearer", "ue", "application", "cell", "system"]
    aggregation_id: str = Field(min_length=1, max_length=128)

    @property
    def key(self) -> tuple[str, str, str]:
        return self.name, self.aggregation_level, self.aggregation_id


class AnalysisPlan(_FrozenStrictModel):
    confidence_level: float = Field(default=0.95, ge=0.5, lt=1.0)
    interval_method: Literal["percentile-bootstrap-v1"] = "percentile-bootstrap-v1"
    bootstrap_resamples: int = Field(ge=200, le=100_000)
    comparison_reference_scheduler: Identifier
    metrics: tuple[MetricSelector, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_metrics(self) -> AnalysisPlan:
        if self.confidence_level != 0.95:
            raise ValueError("experiment contract v1 supports the predeclared 95% confidence level")
        keys = [item.key for item in self.metrics]
        if len(keys) != len(set(keys)):
            raise ValueError("analysis metrics must be unique")
        return self


class ExecutionPlan(_FrozenStrictModel):
    max_workers: int = Field(default=1, ge=1, le=64)
    failure_policy: Literal["retain-and-exclude", "fail-experiment"] = "fail-experiment"


class OutputContract(_FrozenStrictModel):
    artifact_schema_version: Literal["1.0"] = "1.0"
    metric_dataset_schema_version: Literal["1.0"] = "1.0"
    summary_dataset_schema_version: Literal["1.0"] = "1.0"
    plot_manifest_schema_version: Literal["1.0"] = "1.0"


class ExperimentConfig(_FrozenStrictModel):
    schema_version: Literal["1.0"]
    experiment_id: Identifier
    description: str = Field(min_length=1, max_length=500)
    profile: Literal["smoke", "showcase"]
    base_scenario: str = Field(min_length=1, max_length=500)
    timing: Literal["inherit-from-scenario"] = "inherit-from-scenario"
    scheduler_set: tuple[SchedulerLevel, ...] = Field(min_length=2)
    sweep_factors: tuple[SweepFactor, ...] = ()
    seed_plan: SeedPlan
    analysis: AnalysisPlan
    execution: ExecutionPlan
    output: OutputContract = Field(default_factory=OutputContract)

    @model_validator(mode="after")
    def coherent_design(self) -> ExperimentConfig:
        scheduler_ids = [item.level_id for item in self.scheduler_set]
        if len(scheduler_ids) != len(set(scheduler_ids)):
            raise ValueError("scheduler_set level IDs must be unique")
        if self.analysis.comparison_reference_scheduler not in scheduler_ids:
            raise ValueError("comparison reference scheduler must occur in scheduler_set")
        factor_ids = [item.factor_id for item in self.sweep_factors]
        if len(factor_ids) != len(set(factor_ids)):
            raise ValueError("sweep factor IDs must be unique")
        if "scheduler" in factor_ids:
            raise ValueError("scheduler is reserved for scheduler_set")
        return self


@dataclass(frozen=True, slots=True)
class ExperimentSource:
    path: Path
    config: ExperimentConfig
    base_scenario_path: Path
    base_scenario_sha256: str
    experiment_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.config.schema_version,
            "experiment_sha256": self.experiment_sha256,
            "base_scenario_sha256": self.base_scenario_sha256,
            "normalized": self.config.model_dump(mode="json"),
        }


@dataclass(frozen=True, slots=True)
class ExperimentVariant:
    variant_id: str
    factor_levels: tuple[tuple[str, str], ...]
    scenario: NormalizedScenario
    configuration_sha256: str

    def factors_dict(self) -> dict[str, str]:
        return dict(self.factor_levels)


def load_experiment(path: Path) -> ExperimentSource:
    """Load, validate, and content-identify an experiment plus its base scenario."""

    resolved = path.resolve()
    if resolved.suffix.lower() not in {".json", ".yaml", ".yml"}:
        raise ConfigurationFileError(
            "experiment file must use .json, .yaml, or .yml", {"path": str(path)}
        )
    try:
        source_text = resolved.read_text(encoding="utf-8")
        raw = (
            json.loads(source_text)
            if resolved.suffix.lower() == ".json"
            else yaml.safe_load(source_text)
        )
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigurationFileError(
            "unable to read experiment YAML/JSON", {"path": str(path), "detail": str(exc)}
        ) from exc
    if not isinstance(raw, dict):
        raise ConfigurationValidationError(
            "experiment document root must be an object", {"path": str(path)}
        )
    try:
        config = ExperimentConfig.model_validate(raw)
    except ValidationError as exc:
        issues = [
            {
                "field": ".".join(str(part) for part in issue["loc"]),
                "message": issue["msg"],
                "type": issue["type"],
            }
            for issue in exc.errors(include_url=False)
        ]
        raise ConfigurationValidationError(
            f"experiment validation failed with {len(issues)} issue(s)",
            {"path": str(path), "issues": issues},
        ) from exc
    base_path = (resolved.parent / config.base_scenario).resolve()
    base = normalize_scenario(load_scenario(base_path))
    base_sha = build_manifest(base).configuration_sha256
    digest_payload = {
        "base_scenario_sha256": base_sha,
        "experiment": config.model_dump(mode="python"),
    }
    experiment_sha = hashlib.sha256(canonical_json_bytes(digest_payload)).hexdigest()
    return ExperimentSource(resolved, config, base_path, base_sha, experiment_sha)


def expand_variants(source: ExperimentSource) -> tuple[ExperimentVariant, ...]:
    """Expand scheduler and generic factors in authored order, rejecting collisions."""

    base = load_scenario(source.base_scenario_path).model_dump(mode="python")
    dimensions: list[tuple[str, tuple[tuple[str, object], ...]]] = [
        (
            "scheduler",
            tuple(
                (item.level_id, item.scheduler.model_dump(mode="python"))
                for item in source.config.scheduler_set
            ),
        )
    ]
    dimensions.extend(
        (factor.factor_id, tuple((level.level_id, level.value) for level in factor.levels))
        for factor in source.config.sweep_factors
    )
    pointers = {factor.factor_id: factor.json_pointer for factor in source.config.sweep_factors}
    variants: list[ExperimentVariant] = []
    seen_configurations: dict[str, dict[str, str]] = {}

    def visit(index: int, levels: dict[str, str], values: dict[str, object]) -> None:
        if index < len(dimensions):
            factor_id, options = dimensions[index]
            for level_id, value in options:
                visit(index + 1, {**levels, factor_id: level_id}, {**values, factor_id: value})
            return
        scenario_data = copy.deepcopy(base)
        scenario_data["scheduler"] = values["scheduler"]
        for factor_id, pointer in pointers.items():
            _replace_pointer(scenario_data, pointer, values[factor_id])
        try:
            scenario = normalize_scenario(ScenarioConfig.model_validate(scenario_data))
        except ValidationError as exc:
            raise ConfigurationValidationError(
                "a generated experiment variant is not a valid scenario",
                {"factor_levels": levels, "detail": str(exc)},
            ) from exc
        config_sha = build_manifest(scenario).configuration_sha256
        if config_sha in seen_configurations:
            raise ConfigurationValidationError(
                "sweep produced duplicate normalized scenario identities",
                {
                    "first_factor_levels": seen_configurations[config_sha],
                    "duplicate_factor_levels": levels,
                    "configuration_sha256": config_sha,
                    "requirement": "EXP-005",
                },
            )
        seen_configurations[config_sha] = dict(levels)
        identity_payload = {
            "experiment_sha256": source.experiment_sha256,
            "factor_levels": levels,
            "configuration_sha256": config_sha,
        }
        variant_digest = hashlib.sha256(canonical_json_bytes(identity_payload)).hexdigest()
        variants.append(
            ExperimentVariant(
                variant_id=f"variant/{variant_digest}",
                factor_levels=tuple(sorted(levels.items())),
                scenario=scenario,
                configuration_sha256=config_sha,
            )
        )

    visit(0, {}, {})
    return tuple(variants)


def _replace_pointer(document: dict[str, Any], pointer: str, value: object) -> None:
    tokens = [item.replace("~1", "/").replace("~0", "~") for item in pointer[1:].split("/")]
    current: object = document
    for token in tokens[:-1]:
        current = _pointer_child(current, token, pointer)
    leaf = tokens[-1]
    if isinstance(current, dict) and leaf in current:
        current[leaf] = copy.deepcopy(value)
        return
    if isinstance(current, list):
        index = _pointer_index(leaf, len(current), pointer)
        current[index] = copy.deepcopy(value)
        return
    raise ConfigurationValidationError(
        "sweep pointer does not resolve in the base scenario", {"json_pointer": pointer}
    )


def _pointer_child(current: object, token: str, pointer: str) -> object:
    if isinstance(current, dict) and token in current:
        return current[token]
    if isinstance(current, list):
        return current[_pointer_index(token, len(current), pointer)]
    raise ConfigurationValidationError(
        "sweep pointer does not resolve in the base scenario", {"json_pointer": pointer}
    )


def _pointer_index(segment: str, length: int, pointer: str) -> int:
    if not segment.isdecimal() or (segment.startswith("0") and segment != "0"):
        raise ConfigurationValidationError(
            "sweep pointer contains an invalid array index", {"json_pointer": pointer}
        )
    index = int(segment)
    if index >= length:
        raise ConfigurationValidationError(
            "sweep pointer array index is out of range", {"json_pointer": pointer}
        )
    return index
