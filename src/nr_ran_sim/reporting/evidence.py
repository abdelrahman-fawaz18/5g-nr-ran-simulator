"""Create compact, traceable publication snapshots from complete experiment bundles."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from nr_ran_sim.errors import ArtifactError
from nr_ran_sim.experiments.orchestration import _file_sha256, _semantic_sha, _write_json
from nr_ran_sim.experiments.verification import verify_experiment_bundle

EVIDENCE_SNAPSHOT_SCHEMA_VERSION = "1.0"


def publish_evidence_snapshot(bundle_directory: Path, output_directory: Path) -> dict[str, object]:
    """Publish a source-control-sized saved-data view after full bundle verification."""

    source = bundle_directory.resolve()
    target = output_directory.resolve()
    if target.exists():
        raise ArtifactError(
            "evidence snapshot output already exists; choose a new path",
            {"path": str(output_directory)},
        )
    verification = verify_experiment_bundle(source)
    bundle = _load_object(source / "bundle.json")
    stage = target.with_name(f".{target.name}.tmp-{uuid.uuid4().hex}")
    try:
        (stage / "metrics").mkdir(parents=True)
        (stage / "plots").mkdir()
        shutil.copyfile(source / "experiment-manifest.json", stage / "experiment-manifest.json")
        shutil.copyfile(source / "metrics" / "summary.json", stage / "metrics" / "summary.json")
        for plot in (source / "plots").iterdir():
            if plot.is_file():
                shutil.copyfile(plot, stage / "plots" / plot.name)
        _write_json(stage / "verification.json", verification)
        bundle_summary = {
            "schema_version": bundle.get("schema_version"),
            "experiment_id": bundle.get("experiment_id"),
            "experiment_sha256": bundle.get("experiment_sha256"),
            "bundle_semantic_sha256": bundle.get("semantic_sha256"),
            "profile": bundle.get("profile"),
            "code_revision": bundle.get("code_revision"),
            "working_tree_dirty": bundle.get("working_tree_dirty"),
            "started_at_utc": bundle.get("started_at_utc"),
            "completed_at_utc": bundle.get("completed_at_utc"),
            "environment": bundle.get("environment"),
            "execution": bundle.get("execution"),
            "seed_plan": bundle.get("seed_plan"),
            "completeness": bundle.get("completeness"),
            "pairing_checks": bundle.get("pairing_checks"),
            "metric_dataset": bundle.get("metric_dataset"),
            "full_bundle_distribution": {
                "policy": "versioned release asset",
                "source_run_count": verification["counts"]["runs"],  # type: ignore[index]
                "included_in_snapshot": False,
            },
        }
        _write_json(stage / "bundle-summary.json", bundle_summary)
        files = [
            {
                "path": path.relative_to(stage).as_posix(),
                "size_bytes": path.stat().st_size,
                "file_sha256": _file_sha256(path),
            }
            for path in sorted(stage.rglob("*"))
            if path.is_file()
        ]
        manifest: dict[str, object] = {
            "schema_version": EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
            "experiment_id": bundle.get("experiment_id"),
            "experiment_sha256": bundle.get("experiment_sha256"),
            "source_bundle_semantic_sha256": bundle.get("semantic_sha256"),
            "file_count": len(files),
            "files": files,
        }
        manifest["semantic_sha256"] = _semantic_sha(manifest)
        _write_json(stage / "evidence-manifest.json", manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        stage.replace(target)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return manifest


def _load_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(
            "unable to read evidence source artifact",
            {"path": str(path), "detail": str(exc)},
        ) from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ArtifactError("evidence source artifact must be an object", {"path": str(path)})
    return value
