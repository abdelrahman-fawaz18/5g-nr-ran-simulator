"""Schema-first CLI for scenarios, radio diagnostics, and integrated Tier A simulation."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from nr_ran_sim import __version__
from nr_ran_sim.config import ScenarioConfig, build_manifest, load_scenario, normalize_scenario
from nr_ran_sim.config.dynamic import DynamicRadioInput
from nr_ran_sim.errors import ProjectError
from nr_ran_sim.experiments.config import ExperimentConfig, load_experiment
from nr_ran_sim.experiments.dynamic_simulation import run_dynamic_system_simulation
from nr_ran_sim.experiments.orchestration import execute_experiment
from nr_ran_sim.experiments.simulation import run_system_simulation
from nr_ran_sim.experiments.statistics import summarize_experiment
from nr_ran_sim.experiments.verification import verify_experiment_bundle
from nr_ran_sim.metadata import environment_metadata
from nr_ran_sim.observability import configure_logging, log_event
from nr_ran_sim.radio.capacity_snapshot import build_capacity_snapshot
from nr_ran_sim.radio.snapshot import build_radio_snapshot
from nr_ran_sim.reporting import generate_experiment_plots, publish_evidence_snapshot

LOGGER = logging.getLogger("nr_ran_sim.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nr-ran-sim",
        description="Validate scenarios, inspect radio diagnostics, and run Tier A scheduling.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="WARNING",
        help="structured operational-log threshold (default: WARNING)",
    )
    parser.add_argument(
        "--error-format",
        choices=("text", "json"),
        default="text",
        help="render expected failures as text or one JSON object",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser(
        "validate",
        help="validate a scenario and emit its normalized manifest",
    )
    validate.add_argument("scenario", type=Path)
    validate.add_argument("--output", type=Path, help="write normalized JSON to this path")
    validate.add_argument("--force", action="store_true", help="replace an existing output path")
    validate.add_argument(
        "--quiet",
        action="store_true",
        help="suppress manifest stdout (useful with --output)",
    )

    schema = commands.add_parser("schema", help="emit the generated authoring JSON Schema")
    schema.add_argument("--output", type=Path, help="write schema JSON to this path")
    schema.add_argument("--force", action="store_true", help="replace an existing output path")

    dynamic_schema = commands.add_parser(
        "dynamic-schema", help="emit the generated dynamic-radio extension JSON Schema"
    )
    dynamic_schema.add_argument("--output", type=Path, help="write schema JSON to this path")
    dynamic_schema.add_argument(
        "--force", action="store_true", help="replace an existing output path"
    )

    experiment_schema = commands.add_parser(
        "experiment-schema", help="emit the generated experiment JSON Schema"
    )
    experiment_schema.add_argument("--output", type=Path, help="write schema JSON to this path")
    experiment_schema.add_argument(
        "--force", action="store_true", help="replace an existing output path"
    )

    experiment_validate = commands.add_parser(
        "experiment-validate", help="validate and content-identify an experiment manifest"
    )
    experiment_validate.add_argument("experiment", type=Path)
    experiment_validate.add_argument("--output", type=Path, help="write normalized JSON here")
    experiment_validate.add_argument("--force", action="store_true")
    experiment_validate.add_argument("--quiet", action="store_true")

    experiment_run = commands.add_parser(
        "experiment-run", help="execute a saved multi-replication experiment design"
    )
    experiment_run.add_argument("experiment", type=Path)
    experiment_run.add_argument("--output", type=Path, required=True)
    experiment_run.add_argument("--code-revision", required=True)
    experiment_run.add_argument("--working-tree-state", choices=("clean", "dirty"), required=True)
    experiment_run.add_argument("--max-workers", type=int)

    experiment_summarize = commands.add_parser(
        "experiment-summarize", help="derive uncertainty and paired comparisons from saved rows"
    )
    experiment_summarize.add_argument("bundle", type=Path)
    experiment_summarize.add_argument("--allow-partial", action="store_true")

    experiment_plot = commands.add_parser(
        "experiment-plot", help="generate SVG uncertainty plots from a saved summary"
    )
    experiment_plot.add_argument("bundle", type=Path)

    experiment_verify = commands.add_parser(
        "experiment-verify", help="verify bundle, run, metric, summary, and plot integrity"
    )
    experiment_verify.add_argument("bundle", type=Path)
    experiment_verify.add_argument("--output", type=Path, help="write verification JSON here")
    experiment_verify.add_argument("--force", action="store_true")
    experiment_verify.add_argument("--quiet", action="store_true")

    experiment_publish = commands.add_parser(
        "experiment-publish", help="create a compact verified evidence snapshot"
    )
    experiment_publish.add_argument("bundle", type=Path)
    experiment_publish.add_argument("--output", type=Path, required=True)

    snapshot = commands.add_parser(
        "radio-snapshot",
        help="evaluate static topology, propagation, association, and SINR diagnostics",
    )
    snapshot.add_argument("scenario", type=Path)
    snapshot.add_argument(
        "--master-seed",
        required=True,
        help="128-bit hexadecimal seed, for example 0x00000000000000000000000000000001",
    )
    snapshot.add_argument("--replication-id", type=int, required=True)
    snapshot.add_argument("--output", type=Path, help="write canonical snapshot JSON here")
    snapshot.add_argument("--force", action="store_true", help="replace an existing output path")
    snapshot.add_argument(
        "--quiet",
        action="store_true",
        help="suppress snapshot stdout (useful with --output)",
    )

    capacity = commands.add_parser(
        "capacity-snapshot",
        help="evaluate full-allocation CQI, MCS, transport-block, and capacity diagnostics",
    )
    capacity.add_argument("scenario", type=Path)
    capacity.add_argument(
        "--master-seed",
        required=True,
        help="128-bit hexadecimal seed, for example 0x00000000000000000000000000000001",
    )

    simulate = commands.add_parser(
        "simulate",
        help="run the configured static or opt-in dynamic scheduler/queue/KPI pipeline",
    )
    simulate.add_argument("scenario", type=Path)
    simulate.add_argument(
        "--master-seed",
        required=True,
        help="128-bit hexadecimal seed, for example 0x00000000000000000000000000000001",
    )
    simulate.add_argument("--replication-id", type=int, required=True)
    simulate.add_argument(
        "--code-revision",
        required=True,
        help="7-64 hexadecimal Git object ID represented by this execution",
    )
    simulate.add_argument(
        "--working-tree-state",
        choices=("clean", "dirty"),
        required=True,
        help="record whether the supplied code revision had uncommitted changes",
    )
    simulate.add_argument("--output", type=Path, help="write canonical simulation JSON here")
    simulate.add_argument("--force", action="store_true", help="replace an existing output path")
    simulate.add_argument(
        "--quiet",
        action="store_true",
        help="suppress simulation JSON stdout (useful with --output)",
    )
    capacity.add_argument("--replication-id", type=int, required=True)
    capacity.add_argument("--output", type=Path, help="write canonical capacity JSON here")
    capacity.add_argument("--force", action="store_true", help="replace an existing output path")
    capacity.add_argument(
        "--quiet",
        action="store_true",
        help="suppress snapshot stdout (useful with --output)",
    )

    commands.add_parser("environment", help="emit diagnostic runtime metadata")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    try:
        if args.command == "validate":
            return _validate(args)
        if args.command == "schema":
            return _schema(args)
        if args.command == "dynamic-schema":
            return _dynamic_schema(args)
        if args.command == "experiment-schema":
            return _experiment_schema(args)
        if args.command == "experiment-validate":
            return _experiment_validate(args)
        if args.command == "experiment-run":
            return _experiment_run(args)
        if args.command == "experiment-summarize":
            return _experiment_summarize(args)
        if args.command == "experiment-plot":
            return _experiment_plot(args)
        if args.command == "experiment-verify":
            return _experiment_verify(args)
        if args.command == "experiment-publish":
            return _experiment_publish(args)
        if args.command == "radio-snapshot":
            return _radio_snapshot(args)
        if args.command == "capacity-snapshot":
            return _capacity_snapshot(args)
        if args.command == "simulate":
            return _simulate(args)
        if args.command == "environment":
            print(json.dumps(environment_metadata(), sort_keys=True, indent=2))
            return 0
        parser.error(f"unsupported command {args.command}")
    except ProjectError as exc:
        log_event(LOGGER, logging.ERROR, exc.code, **dict(exc.context))
        _render_error(exc, args.error_format)
        return exc.exit_code


def main() -> NoReturn:
    raise SystemExit(run())


def _validate(args: argparse.Namespace) -> int:
    config = load_scenario(args.scenario)
    normalized = normalize_scenario(config)
    manifest = build_manifest(normalized)
    if args.output is not None:
        manifest.write(args.output, force=args.force)
    if not args.quiet:
        sys.stdout.write(manifest.to_json())
    log_event(
        LOGGER,
        logging.INFO,
        "scenario_validated",
        scenario_id=normalized.scenario_id,
        configuration_sha256=manifest.configuration_sha256,
        warning_count=len(normalized.warnings),
    )
    return 0


def _schema(args: argparse.Namespace) -> int:
    return _write_schema(ScenarioConfig.model_json_schema(), args)


def _dynamic_schema(args: argparse.Namespace) -> int:
    return _write_schema(DynamicRadioInput.model_json_schema(), args)


def _experiment_schema(args: argparse.Namespace) -> int:
    return _write_schema(ExperimentConfig.model_json_schema(), args)


def _experiment_validate(args: argparse.Namespace) -> int:
    source = load_experiment(args.experiment)
    payload = json.dumps(source.as_dict(), sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        _write_text_output(args.output, payload, force=args.force)
    if not args.quiet:
        sys.stdout.write(payload)
    return 0


def _experiment_run(args: argparse.Namespace) -> int:
    source = load_experiment(args.experiment)
    bundle = execute_experiment(
        source,
        args.output,
        code_revision=args.code_revision,
        working_tree_dirty=args.working_tree_state == "dirty",
        max_workers=args.max_workers,
    )
    print(
        json.dumps(
            {"bundle": str(args.output), "completeness": bundle["completeness"]}, sort_keys=True
        )
    )
    return 0


def _experiment_summarize(args: argparse.Namespace) -> int:
    summary = summarize_experiment(args.bundle, allow_partial=args.allow_partial)
    print(
        json.dumps(
            {
                "summary": str(args.bundle / "metrics" / "summary.json"),
                "estimate_count": _sequence_length(summary["estimates"], "estimates"),
                "paired_comparison_count": _sequence_length(
                    summary["paired_comparisons"], "paired_comparisons"
                ),
            },
            sort_keys=True,
        )
    )
    return 0


def _experiment_plot(args: argparse.Namespace) -> int:
    manifest = generate_experiment_plots(args.bundle)
    print(
        json.dumps(
            {"plot_directory": str(args.bundle / "plots"), "plot_count": manifest["plot_count"]},
            sort_keys=True,
        )
    )
    return 0


def _experiment_verify(args: argparse.Namespace) -> int:
    report = verify_experiment_bundle(args.bundle)
    payload = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        _write_text_output(args.output, payload, force=args.force)
    if not args.quiet:
        sys.stdout.write(payload)
    return 0


def _experiment_publish(args: argparse.Namespace) -> int:
    manifest = publish_evidence_snapshot(args.bundle, args.output)
    print(
        json.dumps(
            {
                "evidence_snapshot": str(args.output),
                "file_count": manifest["file_count"],
                "semantic_sha256": manifest["semantic_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


def _write_schema(schema: dict[str, object], args: argparse.Namespace) -> int:
    payload = json.dumps(schema, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(payload)
        return 0
    _write_text_output(args.output, payload, force=args.force)
    return 0


def _write_text_output(path: Path, payload: str, *, force: bool) -> None:
    if path.exists() and not force:
        from nr_ran_sim.errors import ArtifactError

        raise ArtifactError(
            "output artifact already exists; pass --force to replace it",
            {"path": str(path)},
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8", newline="\n")


def _radio_snapshot(args: argparse.Namespace) -> int:
    config = load_scenario(args.scenario)
    normalized = normalize_scenario(config)
    snapshot = build_radio_snapshot(
        normalized,
        master_seed=args.master_seed,
        replication_id=args.replication_id,
    )
    if args.output is not None:
        snapshot.write(args.output, force=args.force)
    if not args.quiet:
        sys.stdout.write(snapshot.to_json())
    log_event(
        LOGGER,
        logging.INFO,
        "radio_snapshot_built",
        scenario_id=normalized.scenario_id,
        semantic_sha256=snapshot.semantic_sha256,
        link_count=len(snapshot.links),
        ue_count=len(snapshot.associations),
    )
    return 0


def _capacity_snapshot(args: argparse.Namespace) -> int:
    config = load_scenario(args.scenario)
    normalized = normalize_scenario(config)
    snapshot = build_capacity_snapshot(
        normalized,
        master_seed=args.master_seed,
        replication_id=args.replication_id,
    )
    if args.output is not None:
        snapshot.write(args.output, force=args.force)
    if not args.quiet:
        sys.stdout.write(snapshot.to_json())
    log_event(
        LOGGER,
        logging.INFO,
        "capacity_snapshot_built",
        scenario_id=normalized.scenario_id,
        semantic_sha256=snapshot.semantic_sha256,
        ue_count=len(snapshot.observations),
    )
    return 0


def _simulate(args: argparse.Namespace) -> int:
    config = load_scenario(args.scenario)
    normalized = normalize_scenario(config)
    runner = (
        run_system_simulation
        if normalized.models.fidelity_profile == "tier-a-fr1-static-v1"
        else run_dynamic_system_simulation
    )
    result = runner(
        normalized,
        master_seed=args.master_seed,
        replication_id=args.replication_id,
        code_revision=args.code_revision,
        working_tree_dirty=args.working_tree_state == "dirty",
    )
    if args.output is not None:
        result.write(args.output, force=args.force)
    if not args.quiet:
        sys.stdout.write(result.to_json())
    log_event(
        LOGGER,
        logging.INFO,
        "simulation_completed",
        scenario_id=normalized.scenario_id,
        run_id=str(result.identity.id),
        semantic_sha256=result.semantic_sha256,
        scheduler_policy_id=result.scheduler_policy_id,
        interval_count=len(result.intervals),
        metric_count=len(result.kpis.records),
    )
    return 0


def _render_error(error: ProjectError, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(error.as_dict(), sort_keys=True, ensure_ascii=False), file=sys.stderr)
        return
    print(f"error [{error.code}]: {error.message}", file=sys.stderr)
    for key, value in error.context.items():
        print(f"  {key}: {value}", file=sys.stderr)


def _sequence_length(value: object, field: str) -> int:
    if not isinstance(value, list):
        from nr_ran_sim.errors import ArtifactError

        raise ArtifactError("experiment result field must be a list", {"field": field})
    return len(value)
