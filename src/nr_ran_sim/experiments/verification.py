"""Integrity and lineage verification for completed experiment bundles."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from nr_ran_sim.config.manifest import canonical_json_bytes
from nr_ran_sim.errors import ArtifactError
from nr_ran_sim.experiments.orchestration import _file_sha256, _semantic_sha

VERIFICATION_REPORT_SCHEMA_VERSION = "1.0"


def verify_experiment_bundle(bundle_directory: Path) -> dict[str, object]:
    """Fail closed on bundle, dataset, summary, plot, and source-run integrity errors."""

    root = bundle_directory.resolve()
    bundle = _load_object(root / "bundle.json")
    bundle_semantic = str(bundle.get("semantic_sha256"))
    semantic_input = {
        key: value
        for key, value in bundle.items()
        if key
        not in {
            "semantic_sha256",
            "started_at_utc",
            "completed_at_utc",
            "environment",
        }
    }
    _require_digest(_semantic_sha(semantic_input), bundle_semantic, "bundle semantic digest")
    try:
        complete_marker = (root / "COMPLETE").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ArtifactError(
            "unable to read experiment completion marker",
            {"path": str(root / "COMPLETE"), "detail": str(exc)},
        ) from exc
    _require_digest(bundle_semantic, complete_marker, "completion marker")

    manifest = _load_object(root / "experiment-manifest.json")
    normalized = _object(manifest.get("normalized"), "experiment-manifest.normalized")
    experiment_digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "base_scenario_sha256": manifest.get("base_scenario_sha256"),
                "experiment": normalized,
            }
        )
    ).hexdigest()
    _require_digest(
        experiment_digest,
        str(manifest.get("experiment_sha256")),
        "experiment manifest digest",
    )
    _require_digest(
        experiment_digest, str(bundle.get("experiment_sha256")), "bundle experiment digest"
    )

    completeness = _object(bundle.get("completeness"), "bundle.completeness")
    if completeness.get("status") != "complete":
        raise ArtifactError(
            "experiment bundle is not complete",
            {"completeness": completeness},
        )
    expected_runs = _integer(completeness.get("expected_runs"), "expected_runs")
    successful_runs = _integer(completeness.get("successful_runs"), "successful_runs")
    if successful_runs != expected_runs:
        raise ArtifactError(
            "successful run count does not match the complete design",
            {"expected_runs": expected_runs, "successful_runs": successful_runs},
        )
    pairing = _object(bundle.get("pairing_checks"), "bundle.pairing_checks")
    if pairing.get("status") != "pass" or pairing.get("violations") != 0:
        raise ArtifactError("experiment common-random-number pairing did not pass")

    runs = _list_of_objects(bundle.get("runs"), "bundle.runs")
    if len(runs) != successful_runs:
        raise ArtifactError(
            "run record count does not match bundle completeness",
            {"run_records": len(runs), "successful_runs": successful_runs},
        )
    run_ids: set[str] = set()
    run_hashes: dict[str, str] = {}
    for run in runs:
        run_id = str(run.get("run_id"))
        if run_id in run_ids:
            raise ArtifactError("experiment bundle contains a duplicate run ID", {"run_id": run_id})
        run_ids.add(run_id)
        relative = str(run.get("artifact_path"))
        artifact = _safe_file(root, relative)
        actual_hash = _file_sha256(artifact)
        declared_hash = str(run.get("artifact_sha256"))
        _require_digest(actual_hash, declared_hash, f"run artifact {run_id}")
        run_hashes[relative] = actual_hash

    metric_meta = _object(bundle.get("metric_dataset"), "bundle.metric_dataset")
    metric_path = _safe_file(root, str(metric_meta.get("path")))
    metric_file_hash = _file_sha256(metric_path)
    _require_digest(
        metric_file_hash, str(metric_meta.get("file_sha256")), "replication dataset file"
    )
    dataset = _load_object(metric_path)
    metric_semantic = str(dataset.get("semantic_sha256"))
    _require_digest(
        _semantic_sha({key: value for key, value in dataset.items() if key != "semantic_sha256"}),
        metric_semantic,
        "replication dataset semantic digest",
    )
    _require_digest(
        metric_semantic,
        str(metric_meta.get("semantic_sha256")),
        "bundle replication dataset semantic digest",
    )
    rows = _list_of_objects(dataset.get("rows"), "replication dataset rows")
    if _integer(dataset.get("row_count"), "row_count") != len(rows):
        raise ArtifactError("replication dataset row count is invalid")
    _verify_metric_rows(rows, run_hashes)

    summary_path = root / "metrics" / "summary.json"
    summary = _load_object(summary_path)
    summary_file_hash = _file_sha256(summary_path)
    summary_semantic = str(summary.get("semantic_sha256"))
    _require_digest(
        _semantic_sha({key: value for key, value in summary.items() if key != "semantic_sha256"}),
        summary_semantic,
        "summary semantic digest",
    )
    _require_digest(
        experiment_digest, str(summary.get("experiment_sha256")), "summary experiment digest"
    )
    _require_digest(
        metric_file_hash,
        str(summary.get("source_metric_dataset_file_sha256")),
        "summary source replication file digest",
    )
    _require_digest(
        metric_semantic,
        str(summary.get("source_metric_dataset_semantic_sha256")),
        "summary source replication semantic digest",
    )
    estimates = _list_of_objects(summary.get("estimates"), "summary.estimates")
    comparisons = _list_of_objects(summary.get("paired_comparisons"), "summary.paired_comparisons")

    plot_manifest_path = root / "plots" / "plot-manifest.json"
    plot_manifest = _load_object(plot_manifest_path)
    plot_semantic = str(plot_manifest.get("semantic_sha256"))
    _require_digest(
        _semantic_sha(
            {key: value for key, value in plot_manifest.items() if key != "semantic_sha256"}
        ),
        plot_semantic,
        "plot manifest semantic digest",
    )
    _require_digest(
        experiment_digest,
        str(plot_manifest.get("experiment_sha256")),
        "plot manifest experiment digest",
    )
    _require_digest(
        summary_file_hash,
        str(plot_manifest.get("source_summary_file_sha256")),
        "plot source summary file digest",
    )
    _require_digest(
        summary_semantic,
        str(plot_manifest.get("source_summary_semantic_sha256")),
        "plot source summary semantic digest",
    )
    plots = _list_of_objects(plot_manifest.get("plots"), "plot-manifest.plots")
    if _integer(plot_manifest.get("plot_count"), "plot_count") != len(plots):
        raise ArtifactError("plot manifest count is invalid")
    for plot in plots:
        relative = str(plot.get("path"))
        plot_path = _safe_file(root / "plots", relative)
        _require_digest(
            _file_sha256(plot_path), str(plot.get("file_sha256")), f"plot artifact {relative}"
        )

    return {
        "schema_version": VERIFICATION_REPORT_SCHEMA_VERSION,
        "status": "pass",
        "experiment_id": bundle.get("experiment_id"),
        "experiment_sha256": experiment_digest,
        "bundle_semantic_sha256": bundle_semantic,
        "code_revision": bundle.get("code_revision"),
        "working_tree_dirty": bundle.get("working_tree_dirty"),
        "checks": {
            "bundle_and_complete_marker": "pass",
            "experiment_manifest": "pass",
            "run_artifact_checksums": "pass",
            "replication_rows_and_lineage": "pass",
            "summary_and_lineage": "pass",
            "plots_and_lineage": "pass",
            "common_random_number_pairing": "pass",
        },
        "counts": {
            "runs": len(runs),
            "replication_rows": len(rows),
            "estimates": len(estimates),
            "paired_comparisons": len(comparisons),
            "plots": len(plots),
            "pairing_groups": pairing.get("checked_groups"),
        },
        "digests": {
            "replication_dataset_file_sha256": metric_file_hash,
            "replication_dataset_semantic_sha256": metric_semantic,
            "summary_file_sha256": summary_file_hash,
            "summary_semantic_sha256": summary_semantic,
            "plot_manifest_semantic_sha256": plot_semantic,
        },
    }


def _verify_metric_rows(rows: list[dict[str, object]], run_hashes: dict[str, str]) -> None:
    seen: set[str] = set()
    observations: set[tuple[str, int, str, str, str]] = set()
    for row in rows:
        row_id = str(row.get("row_id"))
        if row_id in seen:
            raise ArtifactError(
                "replication dataset contains a duplicate row ID", {"row_id": row_id}
            )
        seen.add(row_id)
        _require_digest(
            hashlib.sha256(
                canonical_json_bytes({key: value for key, value in row.items() if key != "row_id"})
            ).hexdigest(),
            row_id,
            f"replication row {row_id}",
        )
        value = row.get("value")
        null_reason = row.get("null_reason")
        if value is None and null_reason is None:
            raise ArtifactError("null metric row is missing its reason", {"row_id": row_id})
        if value is not None:
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ArtifactError("metric row value is not finite numeric", {"row_id": row_id})
            if null_reason is not None:
                raise ArtifactError(
                    "metric row has both a value and null reason", {"row_id": row_id}
                )
        replication_id = _integer(row.get("replication_id"), "replication_id")
        observation = (
            str(row.get("variant_id")),
            replication_id,
            str(row.get("name")),
            str(row.get("aggregation_level")),
            str(row.get("aggregation_id")),
        )
        if observation in observations:
            raise ArtifactError("replication dataset contains a duplicate observation")
        observations.add(observation)
        source_path = str(row.get("source_run_artifact"))
        if run_hashes.get(source_path) != row.get("source_run_artifact_sha256"):
            raise ArtifactError(
                "replication row source-run lineage is invalid",
                {"row_id": row_id, "source_run_artifact": source_path},
            )


def _safe_file(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ArtifactError("artifact path escapes its bundle", {"path": relative}) from exc
    if not candidate.is_file():
        raise ArtifactError("expected experiment artifact is missing", {"path": str(candidate)})
    return candidate


def _require_digest(actual: str, expected: str, subject: str) -> None:
    if actual != expected:
        raise ArtifactError(
            "experiment artifact digest mismatch",
            {"subject": subject, "expected": expected, "actual": actual},
        )


def _load_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(
            "unable to read experiment artifact",
            {"path": str(path), "detail": str(exc)},
        ) from exc
    return _object(value, str(path))


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ArtifactError("experiment artifact field must be an object", {"field": field})
    return value


def _list_of_objects(value: object, field: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ArtifactError("experiment artifact field must be a list", {"field": field})
    return [_object(item, field) for item in value]


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int):
        raise ArtifactError("experiment artifact field must be an integer", {"field": field})
    return value
