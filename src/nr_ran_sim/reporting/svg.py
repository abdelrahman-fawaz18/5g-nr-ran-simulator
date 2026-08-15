"""Dependency-light SVG uncertainty plots generated from saved experiment summaries."""

# SVG element strings are intentionally kept as single records for inspectable generated output.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import math
import shutil
import uuid
from html import escape
from pathlib import Path

from nr_ran_sim.config.manifest import canonical_json_bytes
from nr_ran_sim.errors import ArtifactError
from nr_ran_sim.experiments.config import PLOT_MANIFEST_SCHEMA_VERSION
from nr_ran_sim.experiments.orchestration import _file_sha256, _semantic_sha, _write_json

DESIGN_SYSTEM = "systems-lab-v1"
FONT_SANS = "Arial Narrow,Arial,Segoe UI,sans-serif"
FONT_MONO = "Consolas,Courier New,monospace"
BACKGROUND = "#f4f6f8"
PANEL = "#ffffff"
GRID = "#c4cdd7"
TEXT = "#0b1b2b"
MUTED = "#5f6f80"
COBALT = "#2457d6"
STEEL = "#64748b"
AMBER = "#f2a30b"
GREEN = "#16865b"
RED = "#c43d4e"
SCHEDULER_COLORS = {
    "round-robin": COBALT,
    "proportional-fair": STEEL,
    "max-ci": AMBER,
}
SCHEDULER_LABELS = {
    "round-robin": "Round Robin",
    "proportional-fair": "Proportional Fair",
    "max-ci": "Max-C/I",
}


def generate_experiment_plots(bundle_directory: Path) -> dict[str, object]:
    """Render accessible SVGs after validating the saved summary artifact."""

    bundle_path = bundle_directory.resolve()
    summary_path = bundle_path / "metrics" / "summary.json"
    summary = _load_object(summary_path)
    semantic_copy = {key: value for key, value in summary.items() if key != "semantic_sha256"}
    if _semantic_sha(semantic_copy) != summary.get("semantic_sha256"):
        raise ArtifactError("saved summary semantic digest is invalid", {"path": str(summary_path)})
    estimates = summary.get("estimates")
    if not isinstance(estimates, list):
        raise ArtifactError("saved summary estimates must be a list", {"path": str(summary_path)})
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = {}
    for raw in estimates:
        row = _object(raw, "summary estimate")
        metric = _object(row.get("metric"), "summary estimate metric")
        key = (
            str(metric.get("name")),
            str(metric.get("aggregation_level")),
            str(metric.get("aggregation_id")),
            str(row.get("unit")),
        )
        grouped.setdefault(key, []).append(row)
    target = bundle_path / "plots"
    if target.exists():
        raise ArtifactError(
            "plot directory already exists; experiment reporting artifacts are immutable",
            {"path": str(target)},
        )
    stage = bundle_path / f".plots.tmp-{uuid.uuid4().hex}"
    stage.mkdir()
    plot_records: list[dict[str, object]] = []
    try:
        for key in sorted(grouped):
            rows = sorted(grouped[key], key=_label)
            filename = f"{key[0]}--{key[1]}--{_slug(key[2])}.svg"
            plot_path = stage / filename
            svg, plotted = _render_svg(
                rows,
                metric_name=key[0],
                aggregation=f"{key[1]}:{key[2]}",
                unit=key[3],
                experiment_sha256=str(summary["experiment_sha256"]),
                confidence_level=_number(summary["confidence_level"], "confidence_level"),
            )
            plot_path.write_text(svg, encoding="utf-8", newline="\n")
            plot_records.append(
                {
                    "path": filename,
                    "file_sha256": _file_sha256(plot_path),
                    "metric": {
                        "name": key[0],
                        "aggregation_level": key[1],
                        "aggregation_id": key[2],
                        "unit": key[3],
                    },
                    "plotted_points": plotted,
                }
            )
        manifest: dict[str, object] = {
            "schema_version": PLOT_MANIFEST_SCHEMA_VERSION,
            "experiment_sha256": summary["experiment_sha256"],
            "source_summary": "../metrics/summary.json",
            "source_summary_file_sha256": _file_sha256(summary_path),
            "source_summary_semantic_sha256": summary["semantic_sha256"],
            "plot_count": len(plot_records),
            "plots": plot_records,
        }
        manifest["semantic_sha256"] = _semantic_sha(manifest)
        _write_json(stage / "plot-manifest.json", manifest)
        stage.replace(target)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return manifest


def _render_svg(
    rows: list[dict[str, object]],
    *,
    metric_name: str,
    aggregation: str,
    unit: str,
    experiment_sha256: str,
    confidence_level: float,
) -> tuple[str, list[dict[str, object]]]:
    valid = [row for row in rows if row.get("mean") is not None]
    width = 1600
    height = 860
    left, right, top, bottom = 135.0, 65.0, 175.0, 145.0
    plot_width = width - left - right
    plot_height = height - top - bottom
    values = [
        _number(value, "plot value")
        for row in valid
        for value in (
            row.get("confidence_interval_lower"),
            row.get("mean"),
            row.get("confidence_interval_upper"),
        )
        if value is not None
    ]
    minimum = min([0.0, *values])
    maximum = max([0.0, *values])
    if math.isclose(minimum, maximum):
        maximum = minimum + 1.0
    padding = 0.08 * (maximum - minimum)
    y_min = minimum - padding
    y_max = maximum + padding

    def y(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_height

    title = metric_name.replace("_", " ").title()
    factors = [_object(row.get("factor_levels"), "factor_levels") for row in rows]
    structured = bool(factors) and all(
        "scheduler" in factor and "broadband-load" in factor for factor in factors
    )
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc" data-design-system="{DESIGN_SYSTEM}" data-layout="evidence-plot">',
        f'<title id="title">{escape(title)} by experiment variant</title>',
        f'<desc id="desc">Mean and {confidence_level:.0%} deterministic bootstrap confidence interval for {escape(metric_name)} at {escape(aggregation)}.</desc>',
        '<defs><pattern id="engineering-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="#dce2e8" stroke-width="1"/></pattern></defs>',
        f'<rect width="100%" height="100%" fill="{BACKGROUND}"/>',
        '<rect width="100%" height="100%" fill="url(#engineering-grid)" opacity="0.42"/>',
        f'<rect width="100%" height="14" fill="{TEXT}"/>',
        f'<rect y="14" width="100%" height="4" fill="{COBALT}"/>',
        f'<text x="{left}" y="62" font-family="{FONT_SANS}" font-size="18" font-weight="700" letter-spacing="3" fill="{COBALT}">EVIDENCE PLOT / SAVED EXPERIMENT</text>',
        f'<text x="{left}" y="116" font-family="{FONT_SANS}" font-size="38" font-weight="750" fill="{TEXT}">{escape(title)}</text>',
        f'<text x="{left}" y="151" font-family="{FONT_SANS}" font-size="19" fill="{MUTED}">{escape(aggregation)} · mean with {confidence_level:.0%} percentile-bootstrap interval</text>',
    ]
    for tick in range(6):
        tick_value = y_min + (y_max - y_min) * tick / 5
        tick_y = y(tick_value)
        elements.extend(
            [
                f'<line x1="{left}" y1="{tick_y:.2f}" x2="{left + plot_width}" y2="{tick_y:.2f}" stroke="{GRID}" stroke-width="1.5"/>',
                f'<text x="{left - 16}" y="{tick_y + 6:.2f}" text-anchor="end" font-family="{FONT_SANS}" font-size="16" fill="{MUTED}">{escape(_format_number(tick_value))}</text>',
            ]
        )
    plotted: list[dict[str, object]] = []
    if structured:
        load_order = ["light", "nominal", "high", "overload"]
        observed_loads = {str(factor["broadband-load"]) for factor in factors}
        loads = [load for load in load_order if load in observed_loads]
        loads.extend(sorted(observed_loads - set(loads)))
        observed_schedulers = {str(factor["scheduler"]) for factor in factors}
        schedulers = [
            scheduler for scheduler in SCHEDULER_COLORS if scheduler in observed_schedulers
        ]
        schedulers.extend(sorted(observed_schedulers - set(schedulers)))
        row_index = {
            (
                str(_object(row["factor_levels"], "factor_levels")["scheduler"]),
                str(_object(row["factor_levels"], "factor_levels")["broadband-load"]),
            ): row
            for row in rows
        }
        x_positions = {
            load: left + plot_width * index / max(1, len(loads) - 1)
            for index, load in enumerate(loads)
        }
        for load, x_position in x_positions.items():
            elements.append(
                f'<text x="{x_position:.2f}" y="{top + plot_height + 38}" text-anchor="middle" font-family="{FONT_SANS}" font-size="18" font-weight="650" fill="{MUTED}">{escape(load.title())}</text>'
            )
        legend_x = left
        for scheduler_index, scheduler in enumerate(schedulers):
            fallback_colors = (COBALT, STEEL, AMBER, GREEN, RED)
            color = SCHEDULER_COLORS.get(
                scheduler, fallback_colors[scheduler_index % len(fallback_colors)]
            )
            points: list[str] = []
            for load in loads:
                row = row_index[(scheduler, load)]
                mean = row.get("mean")
                lower = row.get("confidence_interval_lower")
                upper = row.get("confidence_interval_upper")
                if mean is None or lower is None or upper is None:
                    continue
                x_position = x_positions[load]
                mean_y = y(_number(mean, "mean"))
                lower_y = y(_number(lower, "confidence_interval_lower"))
                upper_y = y(_number(upper, "confidence_interval_upper"))
                points.append(f"{x_position:.2f},{mean_y:.2f}")
                elements.extend(
                    [
                        f'<line x1="{x_position:.2f}" y1="{upper_y:.2f}" x2="{x_position:.2f}" y2="{lower_y:.2f}" stroke="{color}" stroke-width="2.5"/>',
                        f'<line x1="{x_position - 9:.2f}" y1="{upper_y:.2f}" x2="{x_position + 9:.2f}" y2="{upper_y:.2f}" stroke="{color}" stroke-width="2.5"/>',
                        f'<line x1="{x_position - 9:.2f}" y1="{lower_y:.2f}" x2="{x_position + 9:.2f}" y2="{lower_y:.2f}" stroke="{color}" stroke-width="2.5"/>',
                        f'<rect x="{x_position - 6:.2f}" y="{mean_y - 6:.2f}" width="12" height="12" fill="{PANEL}" stroke="{color}" stroke-width="4"/>',
                    ]
                )
                plotted.append(_plotted_record(row))
            if points:
                elements.append(
                    f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="miter"/>'
                )
            elements.extend(
                [
                    f'<line x1="{legend_x}" y1="{height - 54}" x2="{legend_x + 45}" y2="{height - 54}" stroke="{color}" stroke-width="4"/>',
                    f'<rect x="{legend_x + 17}" y="{height - 59}" width="10" height="10" fill="{PANEL}" stroke="{color}" stroke-width="3"/>',
                    f'<text x="{legend_x + 60}" y="{height - 47}" font-family="{FONT_SANS}" font-size="18" font-weight="650" fill="{TEXT}">{escape(SCHEDULER_LABELS.get(scheduler, scheduler))}</text>',
                ]
            )
            legend_x += 330
    else:
        slot = plot_width / max(1, len(rows))
        bar_width = min(80.0, slot * 0.58)
        for index, row in enumerate(rows):
            x_position = left + slot * (index + 0.5)
            mean = row.get("mean")
            lower = row.get("confidence_interval_lower")
            upper = row.get("confidence_interval_upper")
            if mean is not None and lower is not None and upper is not None:
                mean_value = _number(mean, "mean")
                mean_y = y(mean_value)
                lower_y = y(_number(lower, "confidence_interval_lower"))
                upper_y = y(_number(upper, "confidence_interval_upper"))
                baseline = y(0.0)
                elements.extend(
                    [
                        f'<rect x="{x_position - bar_width / 2:.2f}" y="{min(mean_y, baseline):.2f}" width="{bar_width:.2f}" height="{abs(baseline - mean_y):.2f}" fill="{COBALT}" opacity="0.84"/>',
                        f'<line x1="{x_position:.2f}" y1="{upper_y:.2f}" x2="{x_position:.2f}" y2="{lower_y:.2f}" stroke="{TEXT}" stroke-width="3"/>',
                        f'<line x1="{x_position - 8:.2f}" y1="{upper_y:.2f}" x2="{x_position + 8:.2f}" y2="{upper_y:.2f}" stroke="{TEXT}" stroke-width="3"/>',
                        f'<line x1="{x_position - 8:.2f}" y1="{lower_y:.2f}" x2="{x_position + 8:.2f}" y2="{lower_y:.2f}" stroke="{TEXT}" stroke-width="3"/>',
                    ]
                )
                plotted.append(_plotted_record(row))
            elements.append(
                f'<text x="{x_position:.2f}" y="{top + plot_height + 34}" text-anchor="middle" font-family="{FONT_SANS}" font-size="14" fill="{MUTED}">{escape(str(index + 1))}</text>'
            )
    elements.extend(
        [
            f'<text x="42" y="{top + plot_height / 2}" text-anchor="middle" transform="rotate(-90 42 {top + plot_height / 2})" font-family="{FONT_SANS}" font-size="18" fill="{MUTED}">{escape(unit)}</text>',
            f'<text x="{width - 55}" y="{height - 24}" text-anchor="end" font-family="{FONT_MONO}" font-size="14" fill="{MUTED}">ZERO-INCLUSIVE SCALE / EXPERIMENT {escape(experiment_sha256[:12])}</text>',
            "</svg>\n",
        ]
    )
    return "\n".join(elements), plotted


def _plotted_record(row: dict[str, object]) -> dict[str, object]:
    return {
        "summary_id": row["summary_id"],
        "source_row_ids": row["source_row_ids"],
        "mean": row["mean"],
        "confidence_interval_lower": row["confidence_interval_lower"],
        "confidence_interval_upper": row["confidence_interval_upper"],
    }


def _label(row: dict[str, object]) -> str:
    factors = _object(row.get("factor_levels"), "factor_levels")
    return ", ".join(f"{key}={value}" for key, value in sorted(factors.items()))


def _slug(value: str) -> str:
    safe = "".join(character if character.isalnum() else "-" for character in value.lower())
    trimmed = safe.strip("-")[:48] or "aggregate"
    suffix = hashlib.sha256(canonical_json_bytes(value)).hexdigest()[:8]
    return f"{trimmed}-{suffix}"


def _format_number(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 100_000 or abs(value) < 0.001:
        return f"{value:.2e}"
    return f"{value:.3g}"


def _load_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(
            "unable to read saved summary", {"path": str(path), "detail": str(exc)}
        ) from exc
    return _object(value, str(path))


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ArtifactError("saved reporting field must be an object", {"field": field})
    return value


def _number(value: object, field: str) -> float:
    if not isinstance(value, (int, float)):
        raise ArtifactError("saved reporting field must be numeric", {"field": field})
    return float(value)
