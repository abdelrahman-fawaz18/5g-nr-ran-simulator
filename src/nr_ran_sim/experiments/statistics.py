"""Saved-data validation, deterministic uncertainty, and paired comparisons."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nr_ran_sim.config.manifest import canonical_json_bytes
from nr_ran_sim.errors import ArtifactError, RunExecutionError
from nr_ran_sim.experiments.config import SUMMARY_DATASET_SCHEMA_VERSION
from nr_ran_sim.experiments.orchestration import _file_sha256, _semantic_sha, _write_json
from nr_ran_sim.experiments.seeds import RngStreamRecord, SemanticRngRegistry


def summarize_experiment(
    bundle_directory: Path, *, allow_partial: bool = False
) -> dict[str, object]:
    """Validate saved replication rows and write estimates plus paired differences."""

    bundle_path = bundle_directory.resolve()
    bundle = _load_object(bundle_path / "bundle.json")
    completeness = _object(bundle.get("completeness"), "bundle.completeness")
    if completeness.get("status") != "complete" and not allow_partial:
        raise RunExecutionError(
            "refusing to summarize an incomplete experiment without allow_partial",
            {"path": str(bundle_directory), "completeness": completeness},
        )
    manifest = _load_object(bundle_path / "experiment-manifest.json")
    normalized = _object(manifest.get("normalized"), "experiment-manifest.normalized")
    # Revalidate authoring semantics from the immutable saved manifest, without consulting runs.
    # Loading by path also validates its base reference, so use the schema model through the public
    # loader's source shape already committed in the bundle instead of creating hidden state.
    from nr_ran_sim.experiments.config import ExperimentConfig

    try:
        config = ExperimentConfig.model_validate(normalized)
    except ValidationError as exc:
        raise ArtifactError(
            "saved experiment manifest does not match its declared schema",
            {"path": str(bundle_path / "experiment-manifest.json"), "detail": str(exc)},
        ) from exc
    metric_meta = _object(bundle.get("metric_dataset"), "bundle.metric_dataset")
    metric_relative = str(metric_meta.get("path"))
    metric_path = bundle_path / metric_relative
    if _file_sha256(metric_path) != metric_meta.get("file_sha256"):
        raise ArtifactError(
            "saved replication metric dataset checksum does not match the bundle",
            {"path": str(metric_path)},
        )
    dataset = _load_object(metric_path)
    semantic_copy = {key: value for key, value in dataset.items() if key != "semantic_sha256"}
    if _semantic_sha(semantic_copy) != dataset.get("semantic_sha256"):
        raise ArtifactError(
            "saved replication metric dataset semantic digest is invalid",
            {"path": str(metric_path)},
        )
    raw_rows = dataset.get("rows")
    if not isinstance(raw_rows, list):
        raise ArtifactError("saved metric dataset rows must be a list", {"path": str(metric_path)})
    rows = [_object(item, "metric row") for item in raw_rows]
    anomalies = _validate_rows(rows, bundle_path)
    if anomalies:
        raise ArtifactError(
            "saved metric dataset failed anomaly checks", {"anomalies": anomalies[:20]}
        )
    estimates, estimate_rng = _estimate_rows(config, rows, str(dataset["semantic_sha256"]))
    comparisons, comparison_rng = _comparison_rows(config, rows, str(dataset["semantic_sha256"]))
    summary: dict[str, object] = {
        "schema_version": SUMMARY_DATASET_SCHEMA_VERSION,
        "experiment_id": config.experiment_id,
        "experiment_sha256": bundle["experiment_sha256"],
        "source_metric_dataset": metric_relative,
        "source_metric_dataset_file_sha256": metric_meta["file_sha256"],
        "source_metric_dataset_semantic_sha256": dataset["semantic_sha256"],
        "confidence_level": config.analysis.confidence_level,
        "interval_method": config.analysis.interval_method,
        "bootstrap_resamples": config.analysis.bootstrap_resamples,
        "estimates": estimates,
        "paired_comparisons": comparisons,
        "rng_streams": [
            asdict(item)
            for item in sorted(
                (*estimate_rng, *comparison_rng), key=lambda record: record.semantic_path
            )
        ],
        "anomalies": [],
        "partial_input": completeness.get("status") != "complete",
    }
    summary["semantic_sha256"] = _semantic_sha(summary)
    output_path = bundle_path / "metrics" / "summary.json"
    if output_path.exists():
        raise ArtifactError(
            "summary artifact already exists; experiment bundles are immutable",
            {"path": str(output_path)},
        )
    _write_json(output_path, summary)
    return summary


def _estimate_rows(
    config: Any, rows: list[dict[str, object]], baseline_id: str
) -> tuple[list[dict[str, object]], tuple[RngStreamRecord, ...]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = {}
    for row in rows:
        key = (
            str(row["variant_id"]),
            str(row["name"]),
            str(row["aggregation_level"]),
            str(row["aggregation_id"]),
            str(row["unit"]),
        )
        grouped.setdefault(key, []).append(row)
    registry = SemanticRngRegistry(baseline_id, config.seed_plan.master_seed, 0)
    estimates: list[dict[str, object]] = []
    for key in sorted(grouped):
        group = sorted(
            grouped[key], key=lambda row: _integer(row["replication_id"], "replication_id")
        )
        values = [
            _number(row["value"], "metric value") for row in group if row.get("value") is not None
        ]
        nulls = len(group) - len(values)
        stream_path = f"analysis/estimate/{key[0].removeprefix('variant/')}/{_safe_key(key[1:])}"
        interval, record = _bootstrap_interval(
            values,
            registry,
            stream_path,
            confidence_level=config.analysis.confidence_level,
            resamples=config.analysis.bootstrap_resamples,
        )
        factors = _object(group[0]["factor_levels"], "factor_levels")
        estimates.append(
            {
                "summary_id": _row_digest("estimate", key, factors),
                "kind": "estimate",
                "variant_id": key[0],
                "factor_levels": factors,
                "metric": {"name": key[1], "aggregation_level": key[2], "aggregation_id": key[3]},
                "unit": key[4],
                "n_total": len(group),
                "n_valid": len(values),
                "n_null": nulls,
                "mean": statistics.fmean(values) if values else None,
                "sample_standard_deviation": statistics.stdev(values) if len(values) >= 2 else None,
                "confidence_interval_lower": None if interval is None else interval[0],
                "confidence_interval_upper": None if interval is None else interval[1],
                "source_row_ids": [str(row["row_id"]) for row in group],
                "null_reasons": _null_counts(group),
            }
        )
        if record is None and values:
            raise RunExecutionError("bootstrap interval did not record its RNG stream")
    return estimates, registry.manifest()


def _comparison_rows(
    config: Any, rows: list[dict[str, object]], baseline_id: str
) -> tuple[list[dict[str, object]], tuple[RngStreamRecord, ...]]:
    reference = config.analysis.comparison_reference_scheduler
    schedulers = tuple(item.level_id for item in config.scheduler_set)
    registry = SemanticRngRegistry(baseline_id, config.seed_plan.master_seed, 0)
    indexed: dict[
        tuple[tuple[tuple[str, str], ...], str, str, str, int, str], dict[str, object]
    ] = {}
    for row in rows:
        factors = {
            str(key): str(value) for key, value in _object(row["factor_levels"], "factors").items()
        }
        scheduler = factors.pop("scheduler")
        key = (
            tuple(sorted(factors.items())),
            str(row["name"]),
            str(row["aggregation_level"]),
            str(row["aggregation_id"]),
            _integer(row["replication_id"], "replication_id"),
            scheduler,
        )
        indexed[key] = row
    comparisons: list[dict[str, object]] = []
    strata = sorted({key[:4] for key in indexed})
    for stratum in strata:
        other_factors, name, level, aggregate_id = stratum
        for candidate in schedulers:
            if candidate == reference:
                continue
            pairs: list[tuple[dict[str, object], dict[str, object]]] = []
            for replication_id in config.seed_plan.replication_ids:
                reference_row = indexed.get((*stratum, replication_id, reference))
                candidate_row = indexed.get((*stratum, replication_id, candidate))
                if reference_row is not None and candidate_row is not None:
                    pairs.append((reference_row, candidate_row))
            differences = [
                _number(candidate_row["value"], "candidate metric value")
                - _number(reference_row["value"], "reference metric value")
                for reference_row, candidate_row in pairs
                if reference_row.get("value") is not None and candidate_row.get("value") is not None
            ]
            safe_stratum = _safe_key((str(other_factors), name, level, aggregate_id))
            stream_path = f"analysis/paired/{reference}-vs-{candidate}/{safe_stratum}"
            interval, _ = _bootstrap_interval(
                differences,
                registry,
                stream_path,
                confidence_level=config.analysis.confidence_level,
                resamples=config.analysis.bootstrap_resamples,
            )
            unit = str(pairs[0][0]["unit"]) if pairs else "unknown"
            comparisons.append(
                {
                    "summary_id": _row_digest("paired", stratum, reference, candidate),
                    "kind": "paired_difference",
                    "factor_levels": dict(other_factors),
                    "reference_scheduler": reference,
                    "candidate_scheduler": candidate,
                    "difference_definition": "candidate-minus-reference",
                    "metric": {
                        "name": name,
                        "aggregation_level": level,
                        "aggregation_id": aggregate_id,
                    },
                    "unit": unit,
                    "n_expected_pairs": len(config.seed_plan.replication_ids),
                    "n_valid_pairs": len(differences),
                    "mean_difference": statistics.fmean(differences) if differences else None,
                    "sample_standard_deviation": statistics.stdev(differences)
                    if len(differences) >= 2
                    else None,
                    "confidence_interval_lower": None if interval is None else interval[0],
                    "confidence_interval_upper": None if interval is None else interval[1],
                    "source_row_ids": [str(row["row_id"]) for pair in pairs for row in pair],
                }
            )
    return comparisons, registry.manifest()


def _bootstrap_interval(
    values: list[float],
    registry: SemanticRngRegistry,
    semantic_path: str,
    *,
    confidence_level: float,
    resamples: int,
) -> tuple[tuple[float, float] | None, RngStreamRecord | None]:
    if not values:
        return None, None
    rng = registry.acquire(semantic_path, owner="percentile-bootstrap-v1")
    means = [
        statistics.fmean(values[rng.integer_inclusive(0, len(values) - 1)] for _ in values)
        for _ in range(resamples)
    ]
    alpha = 1.0 - confidence_level
    return (_type7_quantile(means, alpha / 2), _type7_quantile(means, 1 - alpha / 2)), rng.record


def _type7_quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires at least one value")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _validate_rows(rows: list[dict[str, object]], bundle_path: Path) -> list[dict[str, object]]:
    anomalies: list[dict[str, object]] = []
    seen: set[str] = set()
    definitions: dict[tuple[str, str, str], tuple[str, str]] = {}
    observations: set[tuple[str, int, str, str, str]] = set()
    for row in rows:
        row_id = str(row.get("row_id"))
        if row_id in seen:
            anomalies.append({"code": "duplicate_row_id", "row_id": row_id})
        seen.add(row_id)
        semantic = {key: value for key, value in row.items() if key != "row_id"}
        if hashlib.sha256(canonical_json_bytes(semantic)).hexdigest() != row_id:
            anomalies.append({"code": "invalid_row_digest", "row_id": row_id})
        value = row.get("value")
        if value is not None and (
            not isinstance(value, (int, float)) or not math.isfinite(float(value))
        ):
            anomalies.append({"code": "nonfinite_or_non_numeric_value", "row_id": row_id})
        if value is None and row.get("null_reason") is None:
            anomalies.append({"code": "missing_null_reason", "row_id": row_id})
        if value is not None and row.get("null_reason") is not None:
            anomalies.append({"code": "value_with_null_reason", "row_id": row_id})
        key = (
            str(row.get("name")),
            str(row.get("aggregation_level")),
            str(row.get("aggregation_id")),
        )
        definition = (str(row.get("definition_version")), str(row.get("unit")))
        previous = definitions.setdefault(key, definition)
        if previous != definition:
            anomalies.append({"code": "definition_or_unit_mismatch", "metric": key})
        replication_id = row.get("replication_id")
        if isinstance(replication_id, int):
            observation = (str(row.get("variant_id")), replication_id, *key)
            if observation in observations:
                anomalies.append({"code": "duplicate_metric_observation", "metric": key})
            observations.add(observation)
        artifact = bundle_path / str(row.get("source_run_artifact"))
        if not artifact.is_file() or _file_sha256(artifact) != row.get(
            "source_run_artifact_sha256"
        ):
            anomalies.append({"code": "invalid_source_run_artifact", "row_id": row_id})
    return anomalies


def _null_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = row.get("null_reason")
        if reason is not None:
            counts[str(reason)] = counts.get(str(reason), 0) + 1
    return dict(sorted(counts.items()))


def _safe_key(values: tuple[object, ...]) -> str:
    return hashlib.sha256(canonical_json_bytes(values)).hexdigest()[:20]


def _row_digest(*values: object) -> str:
    return hashlib.sha256(canonical_json_bytes(values)).hexdigest()


def _load_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(
            "unable to read saved experiment artifact", {"path": str(path), "detail": str(exc)}
        ) from exc
    return _object(value, str(path))


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ArtifactError("saved experiment artifact field must be an object", {"field": field})
    return value


def _number(value: object, field: str) -> float:
    if not isinstance(value, (int, float)):
        raise ArtifactError("saved metric field must be numeric", {"field": field})
    return float(value)


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int):
        raise ArtifactError("saved metric field must be an integer", {"field": field})
    return value
