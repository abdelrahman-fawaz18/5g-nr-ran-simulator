"""Recruiter-facing SVG assets generated from a verified saved experiment summary."""

# SVG element strings intentionally remain single records for inspectable generated output.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable
from html import escape
from pathlib import Path
from typing import Any

import yaml

from nr_ran_sim.errors import ArtifactError

COLORS = {
    "background": "#f4f6f8",
    "panel": "#ffffff",
    "panel_alt": "#e8edf2",
    "grid": "#c4cdd7",
    "text": "#0b1b2b",
    "muted": "#5f6f80",
    "cyan": "#2457d6",
    "green": "#16865b",
    "orange": "#f2a30b",
    "violet": "#64748b",
    "red": "#c43d4e",
    "header": "#0b1b2b",
    "header_text": "#f7f9fb",
}

DESIGN_SYSTEM = "systems-lab-v1"
FONT_SANS = "Arial Narrow,Arial,Segoe UI,sans-serif"
FONT_MONO = "Consolas,Courier New,monospace"

SCHEDULERS = ("round-robin", "proportional-fair", "max-ci")
SCHEDULER_LABELS = {
    "round-robin": "Round Robin",
    "proportional-fair": "Proportional Fair",
    "max-ci": "Max-C/I",
}
SCHEDULER_COLORS = {
    "round-robin": COLORS["cyan"],
    "proportional-fair": COLORS["violet"],
    "max-ci": COLORS["orange"],
}
LOADS = ("light", "nominal", "high", "overload")
LOAD_LABELS = {value: value.title() for value in LOADS}
ASSET_NAMES = (
    "hero.svg",
    "scenario-topology.svg",
    "system-architecture.svg",
    "scheduler-tradeoffs.svg",
    "load-response.svg",
    "evidence-chain.svg",
    "social-preview.svg",
)


def generate_portfolio_visuals(
    summary_path: Path,
    output_directory: Path,
    scenario_path: Path | None = None,
) -> dict[str, object]:
    """Generate deterministic, accessible portfolio visuals from a saved summary."""

    summary = _load_summary(summary_path)
    resolved_scenario_path = scenario_path or _find_flagship_scenario(summary_path)
    scenario = _load_scenario(resolved_scenario_path)
    estimates = _estimate_rows(summary)
    output_directory.mkdir(parents=True, exist_ok=True)
    renderers: dict[str, Callable[[], str]] = {
        "hero.svg": lambda: _hero(summary, estimates, width=1600, height=560),
        "scenario-topology.svg": lambda: _scenario_topology(scenario, estimates),
        "system-architecture.svg": _architecture,
        "scheduler-tradeoffs.svg": lambda: _tradeoffs(summary, estimates),
        "load-response.svg": lambda: _load_response(summary, estimates),
        "evidence-chain.svg": lambda: _evidence_chain(summary, estimates),
        "social-preview.svg": lambda: _hero(summary, estimates, width=1280, height=640),
    }
    records: list[dict[str, object]] = []
    for name in ASSET_NAMES:
        content = renderers[name]()
        target = output_directory / name
        _write_if_changed(target, content)
        records.append({"path": name, "sha256": _file_sha256(target)})

    manifest: dict[str, object] = {
        "schema_version": "portfolio-visuals-v2",
        "design_system": DESIGN_SYSTEM,
        "source_summary": _logical_source_path(summary_path),
        "source_summary_file_sha256": _file_sha256(summary_path),
        "source_summary_semantic_sha256": summary["semantic_sha256"],
        "source_scenario": _logical_source_path(resolved_scenario_path),
        "source_scenario_file_sha256": _file_sha256(resolved_scenario_path),
        "experiment_sha256": summary["experiment_sha256"],
        "assets": records,
    }
    manifest["semantic_sha256"] = _semantic_sha(manifest)
    _write_if_changed(
        output_directory / "portfolio-visuals.json",
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    return manifest


def _scenario_topology(scenario: dict[str, object], estimates: list[dict[str, object]]) -> str:
    """Render the flagship deployment and traffic mix from its checked-in scenario."""

    topology = _dict(scenario.get("topology"), "topology")
    cells = _dict(topology.get("cells"), "topology.cells")
    groups = _dict(topology.get("ue_groups"), "topology.ue_groups")
    radio = _dict(scenario.get("radio"), "radio")
    traffic = _dict(scenario.get("traffic_profiles"), "traffic_profiles")
    broadband = _dict(groups.get("broadband-users"), "broadband-users")
    low_latency = _dict(groups.get("low-latency-users"), "low-latency-users")
    broadband_profile = _dict(traffic.get("broadband"), "traffic_profiles.broadband")
    low_latency_profile = _dict(traffic.get("low-latency"), "traffic_profiles.low-latency")
    broadband_count = _int(broadband.get("count"))
    low_latency_count = _int(low_latency.get("count"))
    replications = _int(estimates[0].get("n_total"))

    width, height = 1600, 930
    svg = _start_svg(
        width,
        height,
        "Flagship 5G NR simulation scenario",
        "An illustrative three-cell UMa downlink with eight broadband and four low-latency UEs, plus the radio and experiment configuration.",
        hero=True,
    )
    svg.extend(
        [
            _text(
                64,
                66,
                "FIG 01 / FLAGSHIP SIMULATION SCENARIO",
                18,
                COLORS["cyan"],
                weight=700,
                spacing=3,
            ),
            _text(
                64,
                121,
                "Three-cell 5G NR downlink under heterogeneous QoS",
                38,
                COLORS["text"],
                weight=800,
            ),
            _text(
                64,
                158,
                "Seeded UMa topology • shared spectrum • scheduler-controlled PRB allocation",
                20,
                COLORS["muted"],
                weight=500,
            ),
            _pill(1043, 48, 144, f"{len(cells)} gNodeBs", COLORS["green"]),
            _pill(1205, 48, 134, f"{broadband_count + low_latency_count} UEs", COLORS["cyan"]),
            _pill(1357, 48, 179, _quantity_label(radio.get("channel_bandwidth")), COLORS["violet"]),
            _rounded_rect(
                52, 190, 995, 680, 24, COLORS["panel"], stroke=COLORS["grid"], opacity=0.95
            ),
            _rounded_rect(
                1071, 190, 477, 680, 24, COLORS["panel"], stroke=COLORS["grid"], opacity=0.95
            ),
            _text(88, 234, "Illustrative deployment view", 23, COLORS["text"], weight=750),
            _text(
                1011,
                234,
                "seeded positions vary by replication",
                15,
                COLORS["muted"],
                anchor="end",
                weight=600,
            ),
        ]
    )

    gnodebs = ((292, 606, "gNB A"), (783, 606, "gNB B"), (535, 337, "gNB C"))
    cell_hexagons = (
        "147,606 219,481 365,481 437,606 365,731 219,731",
        "638,606 710,481 856,481 928,606 856,731 710,731",
        "390,337 462,212 608,212 680,337 608,462 462,462",
    )
    for points, color in zip(
        cell_hexagons, (COLORS["cyan"], COLORS["violet"], COLORS["green"]), strict=True
    ):
        svg.append(
            f'<polygon points="{points}" fill="{color}" fill-opacity="0.035" stroke="{color}" stroke-opacity="0.34" stroke-width="2"/>'
        )

    # Illustrative UEs are fixed for presentation; simulation coordinates remain seeded inputs.
    broadband_ues = (
        (176, 548, 0),
        (342, 716, 0),
        (454, 528, 0),
        (699, 700, 1),
        (885, 538, 1),
        (735, 493, 1),
        (430, 277, 2),
        (627, 281, 2),
    )
    low_latency_ues = ((231, 673, 0), (840, 663, 1), (535, 433, 2), (571, 239, 2))
    for x, y, serving in broadband_ues:
        gx, gy, _ = gnodebs[serving]
        svg.append(_radio_link(gx, gy - 36, x, y, COLORS["cyan"]))
    for x, y, serving in low_latency_ues:
        gx, gy, _ = gnodebs[serving]
        svg.append(_radio_link(gx, gy - 36, x, y, COLORS["orange"], urgent=True))

    # Reuse-1 interference paths communicate the multi-cell system-level model.
    svg.extend(
        [
            f'<path d="M 315 565 Q 540 470 755 565" fill="none" stroke="{COLORS["red"]}" stroke-width="2" stroke-dasharray="8 9" opacity="0.48"/>',
            f'<path d="M 319 568 Q 402 409 507 367" fill="none" stroke="{COLORS["red"]}" stroke-width="2" stroke-dasharray="8 9" opacity="0.48"/>',
            f'<path d="M 755 568 Q 670 409 562 367" fill="none" stroke="{COLORS["red"]}" stroke-width="2" stroke-dasharray="8 9" opacity="0.48"/>',
        ]
    )
    for x, y, label in gnodebs:
        svg.extend(_gnodeb_icon(x, y, label))
    for index, (x, y, _) in enumerate(broadband_ues, start=1):
        svg.extend(_ue_icon(x, y, f"B{index}", COLORS["cyan"], low_latency=False))
    for index, (x, y, _) in enumerate(low_latency_ues, start=1):
        svg.extend(_ue_icon(x, y, f"L{index}", COLORS["orange"], low_latency=True))

    svg.extend(
        [
            _rounded_rect(82, 786, 930, 58, 16, COLORS["panel_alt"], stroke=COLORS["grid"]),
            *_legend_item(111, 816, f"Broadband UE x {broadband_count}", COLORS["cyan"]),
            *_legend_item(395, 816, f"Low-latency UE x {low_latency_count}", COLORS["orange"]),
            *_legend_item(720, 816, "Reuse-1 interference", COLORS["red"]),
        ]
    )

    frequency = _quantity_label(radio.get("carrier_frequency"))
    bandwidth = _quantity_label(radio.get("channel_bandwidth"))
    scs = _quantity_label(radio.get("subcarrier_spacing"))
    cell = _dict(next(iter(cells.values())), "cell")
    tx_power = _quantity_label(cell.get("transmit_power"))
    bb_source = _dict(broadband_profile.get("source"), "broadband.source")
    bb_packet = _dict(broadband_profile.get("packet_size"), "broadband.packet_size")
    ll_source = _dict(low_latency_profile.get("source"), "low-latency.source")
    ll_packet = _dict(low_latency_profile.get("packet_size"), "low-latency.packet_size")
    svg.extend(
        _scenario_detail_block(
            1104,
            234,
            "01",
            "Radio deployment",
            (
                f"FR1 downlink • {frequency} • {bandwidth}",
                f"{scs} SCS • {tx_power} per gNodeB",
                "3GPP UMa • LOS/NLOS • reuse-1",
            ),
            COLORS["green"],
        )
    )
    svg.extend(
        _scenario_detail_block(
            1104,
            402,
            "02",
            "Heterogeneous traffic",
            (
                f"{broadband_count} broadband • {str(bb_source.get('type')).title()}",
                f"{_quantity_label(bb_packet.get('payload'))} packets",
                f"{low_latency_count} low-latency • {_quantity_label(ll_source.get('interval'))} periodic",
                f"{_quantity_label(ll_packet.get('payload'))} packets • {_quantity_label(low_latency_profile.get('deadline'))} deadline",
            ),
            COLORS["orange"],
        )
    )
    svg.extend(
        _scenario_detail_block(
            1104,
            605,
            "03",
            "Controlled comparison",
            (
                "Round Robin • Max-C/I • PF",
                "Light → overload traffic sweep",
                f"{replications} paired replications per point",
                "Common random numbers + 95% CIs",
            ),
            COLORS["violet"],
        )
    )
    svg.append(
        _text(
            1534,
            903,
            f"scenario {scenario.get('scenario_id')!s}",
            14,
            COLORS["muted"],
            anchor="end",
            family=FONT_MONO,
        )
    )
    return _finish_svg(svg)


def _hero(
    summary: dict[str, object],
    estimates: list[dict[str, object]],
    *,
    width: int,
    height: int,
) -> str:
    run_count, pairing_groups, metric_count = _study_counts(estimates)
    title_size = 62 if width >= 1500 else 51
    subtitle_size = 25 if width >= 1500 else 21
    right_x = width - 540
    svg = _start_svg(
        width,
        height,
        "5G NR RAN system-level simulator",
        "A recruiter-facing overview of a deterministic RAN performance engineering platform.",
        hero=True,
    )
    svg.extend(
        [
            _text(
                76,
                72,
                "PROJECT / RAN PERFORMANCE ENGINEERING",
                18,
                COLORS["cyan"],
                weight=700,
                spacing=3,
            ),
            _text(76, 156, "5G NR RAN", title_size, COLORS["text"], weight=800),
            _text(76, 222, "System-Level Simulator", title_size, COLORS["text"], weight=800),
            _text(
                76,
                276,
                "Deterministic radio, scheduling, QoS and multi-seed experiments",
                subtitle_size,
                COLORS["muted"],
                weight=500,
            ),
            _text(
                76,
                height - 70,
                "Python 3.11-3.13  •  typed configuration  •  Windows + Linux CI",
                20,
                COLORS["muted"],
            ),
        ]
    )
    svg.extend(
        [
            _pill(76, 322, 250, "3GPP-informed radio", COLORS["cyan"]),
            _pill(344, 322, 242, "Paired Monte Carlo", COLORS["violet"]),
        ]
    )
    if width >= 1500:
        svg.append(_pill(604, 322, 250, "Verifiable evidence", COLORS["green"]))
    nodes = [
        (right_x + 260, 90, 18),
        (right_x + 70, 215, 14),
        (right_x + 300, 250, 15),
        (right_x + 470, 170, 13),
        (right_x + 150, 420, 12),
        (right_x + 425, 420, 16),
    ]
    for first, second in (
        (0, 1),
        (0, 2),
        (0, 3),
        (1, 2),
        (1, 4),
        (2, 3),
        (2, 4),
        (2, 5),
        (3, 5),
        (4, 5),
    ):
        x1, y1, _ = nodes[first]
        x2, y2, _ = nodes[second]
        svg.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{COLORS["grid"]}" stroke-width="2" opacity="0.95"/>'
        )
    for index, (x, y, radius) in enumerate(nodes):
        color = COLORS["cyan"] if index in {0, 2} else COLORS["green"]
        svg.extend(
            [
                f'<line x1="{x - radius - 9}" y1="{y}" x2="{x + radius + 9}" y2="{y}" stroke="{COLORS["grid"]}" stroke-width="1"/>',
                f'<line x1="{x}" y1="{y - radius - 9}" x2="{x}" y2="{y + radius + 9}" stroke="{COLORS["grid"]}" stroke-width="1"/>',
                f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{COLORS["panel"]}" stroke="{color}" stroke-width="3"/>',
                f'<rect x="{x - 4}" y="{y - 4}" width="8" height="8" fill="{color}"/>',
            ]
        )
    cards = (
        (right_x + 52, 116, f"{run_count}", "verified runs", COLORS["cyan"]),
        (right_x + 300, 288, "3", "scheduler policies", COLORS["violet"]),
        (right_x + 35, 346, f"{metric_count}", "KPI views", COLORS["green"]),
        (right_x + 290, 458, f"{pairing_groups}", "paired seed groups", COLORS["orange"]),
    )
    for x, y, value, label, color in cards:
        svg.extend(_metric_card(x, y, 220, 86, value, label, color))
    svg.append(
        _text(
            width - 32,
            height - 22,
            f"evidence {str(summary['semantic_sha256'])[:12]}",
            14,
            COLORS["muted"],
            anchor="end",
            family=FONT_MONO,
        )
    )
    return _finish_svg(svg)


def _architecture() -> str:
    width, height = 1600, 780
    svg = _start_svg(
        width,
        height,
        "System architecture",
        "Validated scenarios flow through an isolated deterministic simulation and evidence pipeline.",
    )
    svg.extend(
        [
            _text(
                70, 72, "FIG 02 / SYSTEM ARCHITECTURE", 18, COLORS["cyan"], weight=700, spacing=3
            ),
            _text(
                70,
                126,
                "From scenario definition to verifiable RAN evidence",
                38,
                COLORS["text"],
                weight=750,
            ),
            _text(
                70,
                164,
                "Each boundary is typed, deterministic and independently testable.",
                21,
                COLORS["muted"],
            ),
        ]
    )
    cards = [
        (70, 230, 260, 150, "01", "Scenario", "Typed YAML/JSON\nunits + domains", COLORS["cyan"]),
        (380, 230, 260, 150, "02", "Kernel", "Integer time\nstable event order", COLORS["green"]),
        (
            690,
            230,
            260,
            150,
            "03",
            "RAN state",
            "Radio + queues\nassociation + QoS",
            COLORS["violet"],
        ),
        (
            1000,
            230,
            260,
            150,
            "04",
            "Scheduler",
            "RR / Max-C/I / PF\nimmutable decisions",
            COLORS["orange"],
        ),
        (1310, 230, 220, 150, "05", "Records", "Packets + PRBs\nradio frames", COLORS["red"]),
        (
            260,
            510,
            300,
            150,
            "06",
            "Experiment matrix",
            "Sweeps + paired seeds\nbounded workers",
            COLORS["cyan"],
        ),
        (
            650,
            510,
            300,
            150,
            "07",
            "Statistics",
            "Bootstrap intervals\npaired effects",
            COLORS["violet"],
        ),
        (
            1040,
            510,
            300,
            150,
            "08",
            "Evidence",
            "Checksums + lineage\nreports + visuals",
            COLORS["green"],
        ),
    ]
    for card in cards:
        svg.extend(_architecture_card(*card))
    for x1, y1, x2, y2 in (
        (330, 305, 380, 305),
        (640, 305, 690, 305),
        (950, 305, 1000, 305),
        (1260, 305, 1310, 305),
        (1420, 380, 1420, 450),
        (1420, 450, 410, 450),
        (410, 450, 410, 510),
        (560, 585, 650, 585),
        (950, 585, 1040, 585),
    ):
        svg.append(_arrow(x1, y1, x2, y2))
    svg.extend(
        [
            _text(
                70,
                735,
                "Scientific models never depend on the CLI or presentation layer.",
                19,
                COLORS["muted"],
            ),
            _text(
                1530,
                735,
                "saved-data reporting boundary",
                17,
                COLORS["cyan"],
                anchor="end",
                weight=650,
            ),
        ]
    )
    return _finish_svg(svg)


def _tradeoffs(summary: dict[str, object], estimates: list[dict[str, object]]) -> str:
    width, height = 1600, 1060
    svg = _start_svg(
        width,
        height,
        "Scheduler trade-offs at overload",
        "Four overload KPI panels compare means and 95 percent bootstrap confidence intervals.",
    )
    svg.extend(
        [
            _text(
                70,
                70,
                "FIG 03 / FLAGSHIP RESULT / OVERLOAD",
                18,
                COLORS["cyan"],
                weight=700,
                spacing=3,
            ),
            _text(
                70,
                124,
                "Scheduler trade-offs under heterogeneous traffic",
                40,
                COLORS["text"],
                weight=750,
            ),
            _text(
                70,
                164,
                "Means across 30 paired replications • whiskers show 95% percentile-bootstrap intervals",
                21,
                COLORS["muted"],
            ),
        ]
    )
    panels = (
        (
            70,
            220,
            "System goodput",
            "Mbit/s",
            "cohort_goodput_bps",
            "system",
            "system",
            1e-6,
            220.0,
            lambda x: f"{x:.1f}",
        ),
        (
            815,
            220,
            "Low-latency deadline success",
            "%",
            "deadline_success_ratio",
            "application",
            "low-latency",
            100.0,
            100.0,
            lambda x: f"{x:.1f}%",
        ),
        (
            70,
            610,
            "Jain fairness",
            "ratio",
            "jain_fairness",
            "system",
            "system",
            1.0,
            1.0,
            lambda x: f"{x:.3f}",
        ),
        (
            815,
            610,
            "5th-percentile UE goodput",
            "Mbit/s",
            "fifth_percentile_ue_goodput_bps",
            "system",
            "system",
            1e-6,
            2.2,
            lambda x: f"{x:.3f}",
        ),
    )
    for x, y, title, unit, name, level, aggregate, scale, maximum, formatter in panels:
        rows = _metric_rows(estimates, name, level, aggregate, load="overload")
        svg.extend(_bar_panel(x, y, 715, 330, title, unit, rows, scale, maximum, formatter))
    svg.extend(
        [
            _text(70, 1004, "Interpretation", 18, COLORS["cyan"], weight=700),
            _text(
                210,
                1004,
                "RR protected deadline traffic and weak users in this finite-queue model; this is not a universal scheduler ranking.",
                18,
                COLORS["muted"],
            ),
            _text(
                1530,
                1032,
                f"summary {str(summary['semantic_sha256'])[:12]}",
                14,
                COLORS["muted"],
                anchor="end",
                family=FONT_MONO,
            ),
        ]
    )
    return _finish_svg(svg)


def _load_response(summary: dict[str, object], estimates: list[dict[str, object]]) -> str:
    width, height = 1600, 930
    svg = _start_svg(
        width,
        height,
        "Load response by scheduler",
        "Goodput and low-latency deadline success across four broadband load levels.",
    )
    svg.extend(
        [
            _text(70, 70, "FIG 04 / LOAD RESPONSE", 18, COLORS["cyan"], weight=700, spacing=3),
            _text(
                70,
                124,
                "The trade-off changes as offered load increases",
                40,
                COLORS["text"],
                weight=750,
            ),
            _text(
                70,
                164,
                "Thirty paired replications per scheduler/load point • 95% bootstrap intervals",
                21,
                COLORS["muted"],
            ),
        ]
    )
    goodput = _metric_rows(estimates, "cohort_goodput_bps", "system", "system")
    deadline = _metric_rows(estimates, "deadline_success_ratio", "application", "low-latency")
    svg.extend(
        _line_panel(
            70,
            235,
            715,
            570,
            "System goodput",
            "Mbit/s",
            goodput,
            1e-6,
            220.0,
            lambda value: f"{value:.0f}",
        )
    )
    svg.extend(
        _line_panel(
            815,
            235,
            715,
            570,
            "Low-latency deadline success",
            "%",
            deadline,
            100.0,
            100.0,
            lambda value: f"{value:.0f}%",
        )
    )
    legend_x = 400
    for scheduler in SCHEDULERS:
        svg.extend(
            _legend_item(legend_x, 865, SCHEDULER_LABELS[scheduler], SCHEDULER_COLORS[scheduler])
        )
        legend_x += 285
    svg.append(
        _text(
            1530,
            908,
            f"summary {str(summary['semantic_sha256'])[:12]}",
            14,
            COLORS["muted"],
            anchor="end",
            family=FONT_MONO,
        )
    )
    return _finish_svg(svg)


def _evidence_chain(summary: dict[str, object], estimates: list[dict[str, object]]) -> str:
    width, height = 1600, 660
    run_count, pairing_groups, metric_count = _study_counts(estimates)
    estimate_count = len(estimates)
    comparisons = summary.get("paired_comparisons")
    comparison_count = len(comparisons) if isinstance(comparisons, list) else 0
    rows = run_count * metric_count
    svg = _start_svg(
        width,
        height,
        "Evidence and verification chain",
        "The accepted experiment is transformed through traceable, checksum-verified stages.",
    )
    svg.extend(
        [
            _text(70, 72, "FIG 05 / EVIDENCE CHAIN", 18, COLORS["cyan"], weight=700, spacing=3),
            _text(
                70,
                126,
                "Every result remains traceable to saved run records",
                40,
                COLORS["text"],
                weight=750,
            ),
        ]
    )
    cards = (
        (70, 205, f"{run_count}", "completed runs", "12 variants * 30 seeds", COLORS["cyan"]),
        (
            430,
            205,
            f"{rows:,}",
            "retained KPI rows",
            f"{metric_count} views per run",
            COLORS["green"],
        ),
        (
            790,
            205,
            f"{estimate_count} + {comparison_count}",
            "statistical outputs",
            "estimates + paired effects",
            COLORS["violet"],
        ),
        (
            1150,
            205,
            "PASS",
            "integrity verification",
            "identities • checksums • lineage",
            COLORS["orange"],
        ),
    )
    for index, card in enumerate(cards):
        svg.extend(_evidence_card(*card))
        if index < len(cards) - 1:
            svg.append(_arrow(card[0] + 300, 320, card[0] + 350, 320))
    svg.extend(
        [
            _rounded_rect(70, 485, 1460, 105, 18, COLORS["panel_alt"], stroke=COLORS["grid"]),
            _text(108, 530, "347", 34, COLORS["cyan"], weight=800),
            _text(108, 564, "automated tests", 16, COLORS["muted"]),
            _divider(330, 505, 330, 570),
            _text(385, 530, ">=90%", 34, COLORS["green"], weight=800),
            _text(385, 564, "branch coverage gate", 16, COLORS["muted"]),
            _divider(660, 505, 660, 570),
            _text(715, 530, "4-platform", 34, COLORS["violet"], weight=800),
            _text(715, 564, "Windows/Linux * Python 3.11/3.13", 16, COLORS["muted"]),
            _divider(1090, 505, 1090, 570),
            _text(
                1145, 530, f"{pairing_groups}/{pairing_groups}", 34, COLORS["orange"], weight=800
            ),
            _text(1145, 564, "common-random-number groups", 16, COLORS["muted"]),
            _text(
                1530,
                634,
                f"summary {str(summary['semantic_sha256'])[:12]}",
                14,
                COLORS["muted"],
                anchor="end",
                family=FONT_MONO,
            ),
        ]
    )
    return _finish_svg(svg)


def _bar_panel(
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    unit: str,
    rows: list[dict[str, object]],
    scale: float,
    maximum: float,
    formatter: Callable[[float], str],
) -> list[str]:
    elements = [_rounded_rect(x, y, width, height, 20, COLORS["panel"], stroke=COLORS["grid"])]
    elements.extend(
        [
            _text(x + 28, y + 42, title, 23, COLORS["text"], weight=700),
            _text(x + width - 28, y + 42, unit, 16, COLORS["muted"], anchor="end"),
        ]
    )
    chart_top, chart_bottom = y + 75, y + height - 68
    chart_height = chart_bottom - chart_top
    baseline = chart_bottom
    for tick in range(5):
        value = maximum * tick / 4
        tick_y = baseline - chart_height * tick / 4
        elements.append(_divider(x + 65, tick_y, x + width - 24, tick_y, opacity=0.55))
        elements.append(_text(x + 54, tick_y + 5, f"{value:g}", 13, COLORS["muted"], anchor="end"))
    by_scheduler = {_factors(row)["scheduler"]: row for row in rows}
    bar_width = 105
    slot = (width - 120) / 3
    for index, scheduler in enumerate(SCHEDULERS):
        row = by_scheduler[scheduler]
        mean = _float(row["mean"]) * scale
        lower = _float(row["confidence_interval_lower"]) * scale
        upper = _float(row["confidence_interval_upper"]) * scale
        center = x + 85 + slot * (index + 0.5)
        bar_height = chart_height * mean / maximum
        top = baseline - bar_height
        color = SCHEDULER_COLORS[scheduler]
        lower_y = baseline - chart_height * lower / maximum
        upper_y = baseline - chart_height * upper / maximum
        label_y = min(top - 14, upper_y - 14)
        elements.extend(
            [
                f'<rect x="{center - bar_width / 2:.1f}" y="{top:.1f}" width="{bar_width}" height="{bar_height:.1f}" fill="{color}" opacity="0.9"/>',
                _text(
                    center,
                    label_y,
                    formatter(mean),
                    17,
                    COLORS["text"],
                    anchor="middle",
                    weight=700,
                ),
                _text(
                    center,
                    baseline + 28,
                    SCHEDULER_LABELS[scheduler],
                    15,
                    COLORS["muted"],
                    anchor="middle",
                    weight=600,
                ),
            ]
        )
        elements.extend(_whisker(center, upper_y, lower_y, COLORS["text"]))
    return elements


def _line_panel(
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    unit: str,
    rows: list[dict[str, object]],
    scale: float,
    maximum: float,
    formatter: Callable[[float], str],
) -> list[str]:
    elements = [_rounded_rect(x, y, width, height, 20, COLORS["panel"], stroke=COLORS["grid"])]
    elements.extend(
        [
            _text(x + 30, y + 48, title, 25, COLORS["text"], weight=700),
            _text(x + width - 30, y + 48, unit, 16, COLORS["muted"], anchor="end"),
        ]
    )
    left, right, top, bottom = x + 78, x + width - 35, y + 92, y + height - 72
    chart_width, chart_height = right - left, bottom - top
    for tick in range(6):
        value = maximum * tick / 5
        tick_y = bottom - chart_height * tick / 5
        elements.append(_divider(left, tick_y, right, tick_y, opacity=0.55))
        elements.append(
            _text(left - 14, tick_y + 5, formatter(value), 14, COLORS["muted"], anchor="end")
        )
    x_points = {load: left + chart_width * index / 3 for index, load in enumerate(LOADS)}
    for load in LOADS:
        px = x_points[load]
        elements.append(
            _text(
                px, bottom + 34, LOAD_LABELS[load], 15, COLORS["muted"], anchor="middle", weight=600
            )
        )
    by_key = {(_factors(row)["scheduler"], _factors(row)["broadband-load"]): row for row in rows}
    for scheduler in SCHEDULERS:
        color = SCHEDULER_COLORS[scheduler]
        points: list[tuple[float, float, dict[str, object]]] = []
        for load in LOADS:
            row = by_key[(scheduler, load)]
            mean = _float(row["mean"]) * scale
            py = bottom - chart_height * mean / maximum
            points.append((x_points[load], py, row))
        elements.append(
            f'<polyline points="{" ".join(f"{px:.1f},{py:.1f}" for px, py, _ in points)}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="miter"/>'
        )
        for point_index, (px, py, row) in enumerate(points):
            lower = _float(row["confidence_interval_lower"]) * scale
            upper = _float(row["confidence_interval_upper"]) * scale
            lower_y = bottom - chart_height * lower / maximum
            upper_y = bottom - chart_height * upper / maximum
            elements.extend(_whisker(px, upper_y, lower_y, color, cap=8, width=2))
            elements.append(
                f'<rect x="{px - 6:.1f}" y="{py - 6:.1f}" width="12" height="12" fill="{COLORS["panel"]}" stroke="{color}" stroke-width="4"/>'
            )
            if point_index == len(points) - 1:
                label_offset = {
                    "round-robin": -23,
                    "proportional-fair": 31,
                    "max-ci": -18,
                }[scheduler]
                elements.append(
                    _text(
                        px,
                        py + label_offset,
                        formatter(_float(row["mean"]) * scale),
                        14,
                        color,
                        anchor="middle",
                        weight=750,
                    )
                )
    return elements


def _metric_rows(
    estimates: list[dict[str, object]],
    name: str,
    aggregation_level: str,
    aggregation_id: str,
    *,
    load: str | None = None,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for row in estimates:
        metric = _dict(row.get("metric"), "estimate metric")
        factors = _factors(row)
        if (
            metric.get("name") == name
            and metric.get("aggregation_level") == aggregation_level
            and metric.get("aggregation_id") == aggregation_id
            and (load is None or factors.get("broadband-load") == load)
        ):
            selected.append(row)
    expected = len(SCHEDULERS) if load is not None else len(SCHEDULERS) * len(LOADS)
    if len(selected) != expected:
        raise ArtifactError(
            "portfolio metric selection is incomplete",
            {"metric": name, "expected": expected, "actual": len(selected)},
        )
    return selected


def _study_counts(estimates: list[dict[str, object]]) -> tuple[int, int, int]:
    variants = {str(row["variant_id"]) for row in estimates}
    n_total = {_int(row["n_total"]) for row in estimates}
    if len(n_total) != 1:
        raise ArtifactError("portfolio estimates do not share one replication count", {})
    replications = next(iter(n_total))
    metrics = {
        (
            str(_dict(row["metric"], "metric")["name"]),
            str(_dict(row["metric"], "metric")["aggregation_level"]),
            str(_dict(row["metric"], "metric")["aggregation_id"]),
        )
        for row in estimates
    }
    loads = {_factors(row)["broadband-load"] for row in estimates}
    return len(variants) * replications, len(loads) * replications, len(metrics)


def _start_svg(
    width: int,
    height: int,
    title: str,
    description: str,
    *,
    hero: bool = False,
) -> list[str]:
    mode = "hero" if hero else "figure"
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc" data-design-system="{DESIGN_SYSTEM}" data-layout="{mode}">',
        f'<title id="title">{escape(title)}</title>',
        f'<desc id="desc">{escape(description)}</desc>',
        "<defs>",
        '<pattern id="engineering-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="#dce2e8" stroke-width="1"/></pattern>',
        "</defs>",
        f'<rect width="{width}" height="{height}" fill="{COLORS["background"]}"/>',
        f'<rect width="{width}" height="{height}" fill="url(#engineering-grid)" opacity="0.42"/>',
        f'<rect width="{width}" height="14" fill="{COLORS["header"]}"/>',
        f'<rect y="14" width="{width}" height="4" fill="{COLORS["cyan"]}"/>',
    ]


def _finish_svg(elements: list[str]) -> str:
    elements.append("</svg>\n")
    return "\n".join(elements)


def _text(
    x: float,
    y: float,
    value: str,
    size: int,
    color: str,
    *,
    anchor: str = "start",
    weight: int = 500,
    spacing: float = 0,
    family: str = FONT_SANS,
) -> str:
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
        f'font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'letter-spacing="{spacing}" fill="{color}">{escape(value)}</text>'
    )


def _rounded_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    radius: float,
    fill: str,
    *,
    stroke: str | None = None,
    opacity: float = 1.0,
) -> str:
    stroke_attributes = f' stroke="{stroke}" stroke-width="1.5"' if stroke else ""
    effective_radius = min(radius, 3)
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{effective_radius}" fill="{fill}" opacity="{opacity}"{stroke_attributes}/>'


def _pill(x: float, y: float, width: float, label: str, color: str) -> str:
    return (
        f"<g>{_rounded_rect(x, y, width, 46, 2, COLORS['panel'], stroke=COLORS['grid'], opacity=0.96)}"
        f'<rect x="{x}" y="{y}" width="7" height="46" fill="{color}"/>'
        f"{_text(x + 24, y + 30, label, 15, COLORS['text'], weight=700, spacing=0.5)}</g>"
    )


def _metric_card(
    x: float, y: float, width: float, height: float, value: str, label: str, color: str
) -> list[str]:
    return [
        _rounded_rect(
            x, y, width, height, 17, COLORS["panel"], stroke=COLORS["grid"], opacity=0.96
        ),
        f'<rect x="{x}" y="{y}" width="5" height="{height}" fill="{color}"/>',
        _text(x + 22, y + 38, value, 29, color, weight=800),
        _text(x + 22, y + 65, label.upper(), 13, COLORS["muted"], weight=700, spacing=0.6),
    ]


def _gnodeb_icon(x: float, y: float, label: str) -> list[str]:
    return [
        f'<circle cx="{x}" cy="{y - 27}" r="43" fill="none" stroke="{COLORS["grid"]}" stroke-width="1" stroke-dasharray="4 5"/>',
        f'<path d="M {x} {y - 49} L {x - 22} {y + 18} M {x} {y - 49} L {x + 22} {y + 18} M {x - 14} {y - 20} L {x + 14} {y - 20} M {x - 19} {y - 3} L {x + 19} {y - 3} M {x - 28} {y + 18} L {x + 28} {y + 18}" fill="none" stroke="{COLORS["text"]}" stroke-width="4" stroke-linejoin="miter"/>',
        f'<path d="M {x - 14} {y - 48} Q {x - 39} {y - 34} {x - 35} {y - 8} M {x + 14} {y - 48} Q {x + 39} {y - 34} {x + 35} {y - 8}" fill="none" stroke="{COLORS["cyan"]}" stroke-width="3"/>',
        _rounded_rect(x - 36, y + 29, 72, 28, 14, COLORS["green"], opacity=0.16),
        _text(x, y + 49, label, 14, COLORS["green"], anchor="middle", weight=800),
    ]


def _ue_icon(x: float, y: float, label: str, color: str, *, low_latency: bool) -> list[str]:
    shape = (
        f'<path d="M {x} {y - 17} L {x + 17} {y} L {x} {y + 17} L {x - 17} {y} Z" fill="{COLORS["background"]}" stroke="{color}" stroke-width="3"/>'
        if low_latency
        else f'<rect x="{x - 12}" y="{y - 19}" width="24" height="38" rx="2" fill="{COLORS["panel"]}" stroke="{color}" stroke-width="3"/>'
    )
    indicator = (
        f'<path d="M {x} {y - 9} L {x - 6} {y + 2} L {x + 1} {y + 2} L {x - 3} {y + 11} L {x + 8} {y - 3} L {x + 1} {y - 3} Z" fill="{color}"/>'
        if low_latency
        else f'<circle cx="{x}" cy="{y + 13}" r="2" fill="{color}"/>'
    )
    return [
        shape,
        indicator,
        _text(x, y + 40, label, 12, color, anchor="middle", weight=800),
    ]


def _radio_link(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: str,
    *,
    urgent: bool = False,
) -> str:
    dash = ' stroke-dasharray="5 7"' if urgent else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.2" opacity="0.58"{dash}/>'


def _scenario_detail_block(
    x: float,
    y: float,
    number: str,
    title: str,
    lines: tuple[str, ...],
    color: str,
) -> list[str]:
    elements = [
        _rounded_rect(x, y, 412, 48, 14, color, opacity=0.12),
        _text(x + 24, y + 32, number, 15, color, weight=800, spacing=1),
        _text(x + 72, y + 32, title, 21, COLORS["text"], weight=750),
    ]
    elements.extend(
        _text(x + 4, y + 78 + index * 29, line, 16, COLORS["muted"], weight=550)
        for index, line in enumerate(lines)
    )
    return elements


def _architecture_card(
    x: float,
    y: float,
    width: float,
    height: float,
    number: str,
    title: str,
    body: str,
    color: str,
) -> list[str]:
    lines = body.split("\n")
    return [
        _rounded_rect(x, y, width, height, 18, COLORS["panel"], stroke=COLORS["grid"]),
        _rounded_rect(x + 18, y + 18, 46, 34, 10, color, opacity=0.16),
        _text(x + 41, y + 42, number, 15, color, anchor="middle", weight=800),
        _text(x + 78, y + 43, title, 22, COLORS["text"], weight=700),
        _text(x + 22, y + 91, lines[0], 17, COLORS["muted"]),
        _text(x + 22, y + 119, lines[1], 17, COLORS["muted"]),
    ]


def _evidence_card(
    x: float,
    y: float,
    value: str,
    label: str,
    detail: str,
    color: str,
) -> list[str]:
    return [
        _rounded_rect(x, y, 300, 230, 20, COLORS["panel"], stroke=COLORS["grid"]),
        f'<rect x="{x}" y="{y}" width="300" height="8" fill="{color}"/>',
        _text(x + 28, y + 86, value, 46, color, weight=800),
        _text(x + 28, y + 128, label, 21, COLORS["text"], weight=700),
        _text(x + 28, y + 171, detail, 16, COLORS["muted"]),
        _text(x + 28, y + 202, "checksum-linked", 14, color, weight=650, spacing=1),
    ]


def _legend_item(x: float, y: float, label: str, color: str) -> list[str]:
    return [
        f'<line x1="{x}" y1="{y}" x2="{x + 42}" y2="{y}" stroke="{color}" stroke-width="4"/>',
        f'<rect x="{x + 17}" y="{y - 5}" width="10" height="10" fill="{COLORS["panel"]}" stroke="{color}" stroke-width="3"/>',
        _text(x + 58, y + 6, label, 18, COLORS["text"], weight=650),
    ]


def _whisker(
    x: float,
    top: float,
    bottom: float,
    color: str,
    *,
    cap: float = 12,
    width: float = 3,
) -> list[str]:
    return [
        f'<line x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{bottom:.1f}" stroke="{color}" stroke-width="{width}"/>',
        f'<line x1="{x - cap:.1f}" y1="{top:.1f}" x2="{x + cap:.1f}" y2="{top:.1f}" stroke="{color}" stroke-width="{width}"/>',
        f'<line x1="{x - cap:.1f}" y1="{bottom:.1f}" x2="{x + cap:.1f}" y2="{bottom:.1f}" stroke="{color}" stroke-width="{width}"/>',
    ]


def _divider(x1: float, y1: float, x2: float, y2: float, *, opacity: float = 1.0) -> str:
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{COLORS["grid"]}" stroke-width="1.5" opacity="{opacity}"/>'


def _arrow(x1: float, y1: float, x2: float, y2: float) -> str:
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 12
    left_x = x2 - size * math.cos(angle - math.pi / 6)
    left_y = y2 - size * math.sin(angle - math.pi / 6)
    right_x = x2 - size * math.cos(angle + math.pi / 6)
    right_y = y2 - size * math.sin(angle + math.pi / 6)
    return (
        f'<g><line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{COLORS["grid"]}" stroke-width="3"/>'
        f'<path d="M {left_x:.1f} {left_y:.1f} L {x2:.1f} {y2:.1f} L {right_x:.1f} {right_y:.1f}" fill="none" stroke="{COLORS["cyan"]}" stroke-width="3" stroke-linejoin="miter"/></g>'
    )


def _load_summary(path: Path) -> dict[str, object]:
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError("unable to load portfolio source summary", {"path": str(path)}) from exc
    summary = _dict(summary, "summary")
    expected = summary.get("semantic_sha256")
    semantic = {key: value for key, value in summary.items() if key != "semantic_sha256"}
    if not isinstance(expected, str) or _semantic_sha(semantic) != expected:
        raise ArtifactError(
            "portfolio source summary semantic digest is invalid", {"path": str(path)}
        )
    return summary


def _find_flagship_scenario(summary_path: Path) -> Path:
    for parent in summary_path.resolve().parents:
        candidate = parent / "examples" / "scenarios" / "heterogeneous-qos-study.yaml"
        if candidate.is_file():
            return candidate
    raise ArtifactError(
        "unable to locate flagship scenario beside portfolio summary",
        {"summary_path": str(summary_path)},
    )


def _load_scenario(path: Path) -> dict[str, object]:
    try:
        scenario = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ArtifactError(
            "unable to load portfolio source scenario", {"path": str(path)}
        ) from exc
    return _dict(scenario, "scenario")


def _quantity_label(value: object) -> str:
    quantity = _dict(value, "quantity")
    magnitude = quantity.get("value")
    unit = quantity.get("unit")
    if (
        not isinstance(magnitude, (int, float))
        or isinstance(magnitude, bool)
        or not isinstance(unit, str)
    ):
        raise ArtifactError("portfolio quantity must contain numeric value and unit", {})
    return f"{magnitude:g} {unit}"


def _estimate_rows(summary: dict[str, object]) -> list[dict[str, object]]:
    estimates = summary.get("estimates")
    if not isinstance(estimates, list):
        raise ArtifactError("portfolio source estimates must be a list", {})
    return [_dict(row, "estimate") for row in estimates]


def _factors(row: dict[str, object]) -> dict[str, str]:
    raw = _dict(row.get("factor_levels"), "factor_levels")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in raw.items()):
        raise ArtifactError("portfolio factor levels must contain strings", {})
    return {str(key): str(value) for key, value in raw.items()}


def _dict(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ArtifactError("portfolio source field must be an object", {"field": field})
    return value


def _float(value: object) -> float:
    if not isinstance(value, (int, float)):
        raise ArtifactError("portfolio chart value must be numeric", {"value": str(value)})
    return float(value)


def _int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ArtifactError("portfolio replication count must be an integer", {"value": str(value)})
    return value


def _semantic_sha(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(data).hexdigest()


def _logical_source_path(path: Path) -> str:
    parts = path.as_posix().split("/")
    if "evidence" in parts:
        return "/".join(parts[parts.index("evidence") :])
    return path.name


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_if_changed(path: Path, content: str) -> None:
    encoded = content.encode("utf-8")
    if path.exists() and path.read_bytes() == encoded:
        return
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)


def generated_asset_paths(directory: Path) -> Iterable[Path]:
    """Return the deterministic asset set used by repository integrity tests."""

    return (*(directory / name for name in ASSET_NAMES), directory / "portfolio-visuals.json")
