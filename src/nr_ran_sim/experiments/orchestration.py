"""Deterministic multi-run orchestration and immutable experiment bundles."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from collections.abc import Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nr_ran_sim.config.manifest import canonical_json_bytes
from nr_ran_sim.errors import ArtifactError, ProjectError, RunExecutionError
from nr_ran_sim.experiments.config import (
    EXPERIMENT_ARTIFACT_SCHEMA_VERSION,
    METRIC_DATASET_SCHEMA_VERSION,
    ExperimentSource,
    ExperimentVariant,
    expand_variants,
)
from nr_ran_sim.experiments.dynamic_simulation import (
    DynamicSimulationResult,
    run_dynamic_system_simulation,
)
from nr_ran_sim.experiments.simulation import SimulationResult, run_system_simulation
from nr_ran_sim.metadata import environment_metadata
from nr_ran_sim.metrics.records import MetricRecord

SimulationOutput = SimulationResult | DynamicSimulationResult
_CODE_REVISION = re.compile(r"^[0-9a-fA-F]{7,64}$")


@dataclass(frozen=True, slots=True)
class _RunCell:
    variant: ExperimentVariant
    replication_id: int


@dataclass(frozen=True, slots=True)
class _RunSuccess:
    cell: _RunCell
    result: SimulationOutput


@dataclass(frozen=True, slots=True)
class _RunFailure:
    cell: _RunCell
    error_code: str
    message: str
    context: dict[str, object]


def execute_experiment(
    source: ExperimentSource,
    output_directory: Path,
    *,
    code_revision: str,
    working_tree_dirty: bool,
    max_workers: int | None = None,
) -> dict[str, object]:
    """Execute a complete factorial design and atomically publish its saved bundle."""

    target = output_directory.resolve()
    if not _CODE_REVISION.fullmatch(code_revision):
        from nr_ran_sim.errors import ConfigurationValidationError

        raise ConfigurationValidationError(
            "code revision must be a 7-64 character hexadecimal Git object ID",
            {"field": "code_revision", "requirement": "EXP-006"},
        )
    if target.exists():
        raise ArtifactError(
            "experiment output directory already exists; choose a new path",
            {"path": str(output_directory), "requirement": "OPS-007"},
        )
    variants = expand_variants(source)
    cells = tuple(
        _RunCell(variant, replication_id)
        for variant in variants
        for replication_id in source.config.seed_plan.replication_ids
    )
    worker_count = source.config.execution.max_workers if max_workers is None else max_workers
    if not 1 <= worker_count <= 64:
        raise RunExecutionError(
            "max_workers must be between 1 and 64", {"max_workers": worker_count}
        )
    stage = target.with_name(f".{target.name}.tmp-{uuid.uuid4().hex}")
    stage.mkdir(parents=True)
    started_at = _utc_now()
    try:
        outcomes = _execute_cells(
            cells,
            source,
            code_revision=code_revision,
            working_tree_dirty=working_tree_dirty,
            max_workers=worker_count,
        )
        bundle = _write_bundle(
            stage,
            source,
            variants,
            outcomes,
            code_revision=code_revision,
            working_tree_dirty=working_tree_dirty,
            max_workers=worker_count,
            started_at=started_at,
        )
        stage.replace(target)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    failed = int(bundle["completeness"]["failed_runs"])  # type: ignore[index]
    if failed and source.config.execution.failure_policy == "fail-experiment":
        raise RunExecutionError(
            "experiment bundle retained one or more failed replications",
            {"path": str(target), "failed_runs": failed, "requirement": "EXP-008"},
        )
    return bundle


def _execute_cells(
    cells: tuple[_RunCell, ...],
    source: ExperimentSource,
    *,
    code_revision: str,
    working_tree_dirty: bool,
    max_workers: int,
) -> Iterator[_RunSuccess | _RunFailure]:
    if max_workers == 1:
        for cell in cells:
            yield _execute_cell(
                cell,
                source,
                code_revision=code_revision,
                working_tree_dirty=working_tree_dirty,
            )
        return
    cell_iterator = iter(cells)
    pending: dict[Future[_RunSuccess | _RunFailure], _RunCell] = {}
    with ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix="nr-ran-experiment"
    ) as pool:

        def submit_next() -> bool:
            try:
                cell = next(cell_iterator)
            except StopIteration:
                return False
            pending[
                pool.submit(
                    _execute_cell,
                    cell,
                    source,
                    code_revision=code_revision,
                    working_tree_dirty=working_tree_dirty,
                )
            ] = cell
            return True

        for _ in range(min(max_workers, len(cells))):
            submit_next()
        while pending:
            completed, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in completed:
                pending.pop(future)
                outcome = future.result()
                submit_next()
                yield outcome


def _execute_cell(
    cell: _RunCell,
    source: ExperimentSource,
    *,
    code_revision: str,
    working_tree_dirty: bool,
) -> _RunSuccess | _RunFailure:
    factors = cell.variant.factors_dict()
    try:
        runner = (
            run_system_simulation
            if cell.variant.scenario.models.fidelity_profile == "tier-a-fr1-static-v1"
            else run_dynamic_system_simulation
        )
        result = runner(
            cell.variant.scenario,
            master_seed=source.config.seed_plan.master_seed,
            replication_id=cell.replication_id,
            code_revision=code_revision,
            working_tree_dirty=working_tree_dirty,
            experiment_factors=factors,
        )
    except ProjectError as exc:
        return _RunFailure(cell, exc.code, exc.message, dict(exc.context))
    except Exception as exc:  # defensive run boundary: failures must remain auditable
        return _RunFailure(cell, "unexpected_run_failure", str(exc), {"type": type(exc).__name__})
    return _RunSuccess(cell, result)


def _write_bundle(
    stage: Path,
    source: ExperimentSource,
    variants: tuple[ExperimentVariant, ...],
    outcomes: Iterable[_RunSuccess | _RunFailure],
    *,
    code_revision: str,
    working_tree_dirty: bool,
    max_workers: int,
    started_at: str,
) -> dict[str, object]:
    runs_directory = stage / "runs"
    metrics_directory = stage / "metrics"
    runs_directory.mkdir()
    metrics_directory.mkdir()
    _write_json(stage / "experiment-manifest.json", source.as_dict())
    run_records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    run_ids: set[str] = set()
    for outcome in outcomes:
        if isinstance(outcome, _RunFailure):
            failures.append(_failure_dict(outcome))
            continue
        result = outcome.result
        run_id = str(result.identity.id)
        if run_id in run_ids:
            raise RunExecutionError(
                "experiment generated a duplicate run identity",
                {"run_id": run_id, "requirement": "EXP-005"},
            )
        run_ids.add(run_id)
        relative_path = Path("runs") / f"{run_id.removeprefix('run/')}.json"
        run_path = stage / relative_path
        result.write(run_path)
        file_sha = _file_sha256(run_path)
        run_records.append(
            {
                "variant_id": outcome.cell.variant.variant_id,
                "factor_levels": outcome.cell.variant.factors_dict(),
                "replication_id": outcome.cell.replication_id,
                "run_id": run_id,
                "run_semantic_sha256": result.semantic_sha256,
                "exogenous_configuration_sha256": result.exogenous_configuration_sha256,
                "artifact_path": relative_path.as_posix(),
                "artifact_sha256": file_sha,
            }
        )
        metric_rows.extend(_metric_rows(source, outcome, relative_path.as_posix(), file_sha))
    run_records.sort(key=_artifact_sort_key)
    failures.sort(key=_artifact_sort_key)
    metric_rows.sort(key=lambda item: str(item["row_id"]))
    metric_payload = {
        "schema_version": METRIC_DATASET_SCHEMA_VERSION,
        "experiment_sha256": source.experiment_sha256,
        "row_count": len(metric_rows),
        "rows": metric_rows,
    }
    metric_payload["semantic_sha256"] = _semantic_sha(metric_payload)
    metric_path = metrics_directory / "replications.json"
    _write_json(metric_path, metric_payload)
    expected = len(variants) * len(source.config.seed_plan.replication_ids)
    successful = len(run_records)
    failed = len(failures)
    completeness = {
        "expected_runs": expected,
        "successful_runs": successful,
        "failed_runs": failed,
        "missing_runs": expected - successful - failed,
        "duplicate_run_ids": 0,
        "status": "complete" if successful == expected else "partial",
    }
    pairing_checks = _pairing_checks(run_records)
    variant_records = [
        {
            "variant_id": variant.variant_id,
            "factor_levels": variant.factors_dict(),
            "configuration_sha256": variant.configuration_sha256,
            "timing_ns": {
                "warmup": variant.scenario.simulation.measurement_start_ns,
                "measurement": (
                    variant.scenario.simulation.measurement_end_ns
                    - variant.scenario.simulation.measurement_start_ns
                ),
                "drain": (
                    variant.scenario.simulation.stop_ns
                    - variant.scenario.simulation.measurement_end_ns
                ),
            },
        }
        for variant in variants
    ]
    bundle: dict[str, object] = {
        "schema_version": EXPERIMENT_ARTIFACT_SCHEMA_VERSION,
        "experiment_id": source.config.experiment_id,
        "experiment_sha256": source.experiment_sha256,
        "profile": source.config.profile,
        "code_revision": code_revision,
        "working_tree_dirty": working_tree_dirty,
        "started_at_utc": started_at,
        "completed_at_utc": _utc_now(),
        "environment": environment_metadata(),
        "execution": {
            "parallelism": "isolated-thread-workers-v1",
            "max_workers": max_workers,
            "failure_policy": source.config.execution.failure_policy,
        },
        "seed_plan": source.config.seed_plan.model_dump(mode="json"),
        "variants": variant_records,
        "runs": run_records,
        "failed_replications": failures,
        "completeness": completeness,
        "pairing_checks": pairing_checks,
        "metric_dataset": {
            "path": "metrics/replications.json",
            "file_sha256": _file_sha256(metric_path),
            "semantic_sha256": metric_payload["semantic_sha256"],
        },
    }
    bundle["semantic_sha256"] = _semantic_sha(
        {
            key: value
            for key, value in bundle.items()
            if key not in {"started_at_utc", "completed_at_utc", "environment"}
        }
    )
    _write_json(stage / "bundle.json", bundle)
    _write_text(stage / "COMPLETE", f"{bundle['semantic_sha256']}\n")
    return bundle


def _metric_rows(
    source: ExperimentSource,
    outcome: _RunSuccess,
    artifact_path: str,
    artifact_sha256: str,
) -> list[dict[str, object]]:
    selected = {item.key for item in source.config.analysis.metrics}
    records: list[MetricRecord] = list(outcome.result.kpis.records)
    if isinstance(outcome.result, DynamicSimulationResult):
        records.extend(outcome.result.dynamic_kpis.records)
    matching = [
        record
        for record in records
        if (record.name, record.aggregation_level, record.aggregation_id) in selected
    ]
    found = {(item.name, item.aggregation_level, item.aggregation_id) for item in matching}
    missing = sorted(selected - found)
    if missing:
        raise RunExecutionError(
            "selected experiment metrics are absent from a successful run",
            {
                "variant_id": outcome.cell.variant.variant_id,
                "replication_id": outcome.cell.replication_id,
                "missing": missing,
            },
        )
    rows: list[dict[str, object]] = []
    for record in matching:
        row: dict[str, object] = {
            "experiment_id": source.config.experiment_id,
            "experiment_sha256": source.experiment_sha256,
            "variant_id": outcome.cell.variant.variant_id,
            "factor_levels": outcome.cell.variant.factors_dict(),
            "replication_id": outcome.cell.replication_id,
            "run_id": str(outcome.result.identity.id),
            "run_semantic_sha256": outcome.result.semantic_sha256,
            "source_run_artifact": artifact_path,
            "source_run_artifact_sha256": artifact_sha256,
            **record.as_dict(),
        }
        row["row_id"] = hashlib.sha256(canonical_json_bytes(row)).hexdigest()
        rows.append(row)
    return rows


def _failure_dict(outcome: _RunFailure) -> dict[str, object]:
    return {
        "variant_id": outcome.cell.variant.variant_id,
        "factor_levels": outcome.cell.variant.factors_dict(),
        "replication_id": outcome.cell.replication_id,
        "error": {
            "code": outcome.error_code,
            "message": outcome.message,
            "context": outcome.context,
        },
    }


def _pairing_checks(run_records: list[dict[str, object]]) -> dict[str, object]:
    groups: dict[tuple[tuple[tuple[str, str], ...], int], set[str]] = {}
    for record in run_records:
        factors_raw = record["factor_levels"]
        if not isinstance(factors_raw, dict):
            raise RunExecutionError("run record factor levels must be an object")
        factors = {str(key): str(value) for key, value in factors_raw.items()}
        factors.pop("scheduler", None)
        replication_id = record["replication_id"]
        if not isinstance(replication_id, int):
            raise RunExecutionError("run record replication ID must be an integer")
        key = tuple(sorted(factors.items())), replication_id
        groups.setdefault(key, set()).add(str(record["exogenous_configuration_sha256"]))
    violations = [
        {"factor_levels": dict(key[0]), "replication_id": key[1], "exogenous_ids": sorted(ids)}
        for key, ids in sorted(groups.items())
        if len(ids) != 1
    ]
    if violations:
        raise RunExecutionError(
            "scheduler comparison did not preserve common exogenous inputs",
            {"violations": violations, "requirement": "EXP-004"},
        )
    return {
        "method": "common-random-numbers-v1",
        "checked_groups": len(groups),
        "violations": 0,
        "status": "pass",
    }


def _artifact_sort_key(item: dict[str, object]) -> tuple[str, int]:
    replication_id = item["replication_id"]
    if not isinstance(replication_id, int):
        raise RunExecutionError("replication artifact contains a noninteger replication ID")
    return str(item["variant_id"]), replication_id


def _semantic_sha(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    _write_text(
        path,
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
    )


def _write_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
