from __future__ import annotations

import json
import shutil
from pathlib import Path

from tests.conftest import REPOSITORY_ROOT

from nr_ran_sim.reporting.portfolio import ASSET_NAMES, generate_portfolio_visuals
from nr_ran_sim.reporting.svg import generate_experiment_plots

SUMMARY = REPOSITORY_ROOT / "evidence" / "scheduler-study-v1" / "metrics" / "summary.json"
SCENARIO = REPOSITORY_ROOT / "examples" / "scenarios" / "heterogeneous-qos-study.yaml"
COMMITTED = REPOSITORY_ROOT / "docs" / "assets"
COMMITTED_EVIDENCE_PLOTS = REPOSITORY_ROOT / "evidence" / "scheduler-study-v1" / "plots"


def test_portfolio_visuals_are_accessible_deterministic_and_current(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = generate_portfolio_visuals(SUMMARY, first)
    second_manifest = generate_portfolio_visuals(SUMMARY, second)

    assert first_manifest == second_manifest
    assert first_manifest["schema_version"] == "portfolio-visuals-v2"
    assert first_manifest["design_system"] == "systems-lab-v1"
    assert (
        first_manifest["source_summary_semantic_sha256"]
        == json.loads(SUMMARY.read_text(encoding="utf-8"))["semantic_sha256"]
    )
    assert first_manifest["source_scenario_file_sha256"]
    for name in ASSET_NAMES:
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert (first / name).read_bytes() == (COMMITTED / name).read_bytes()
        text = (first / name).read_text(encoding="utf-8")
        assert 'role="img"' in text
        assert 'aria-labelledby="title desc"' in text
        assert '<title id="title">' in text
        assert '<desc id="desc">' in text
        assert 'data-design-system="systems-lab-v1"' in text
        assert "#f4f6f8" in text
        assert "Arial Narrow" in text
        assert "<linearGradient" not in text
        assert 'filter id="glow"' not in text

    assert (first / "portfolio-visuals.json").read_bytes() == (
        COMMITTED / "portfolio-visuals.json"
    ).read_bytes()


def test_portfolio_charts_retain_large_readable_typography(tmp_path: Path) -> None:
    generate_portfolio_visuals(SUMMARY, tmp_path)
    for name in ("scheduler-tradeoffs.svg", "load-response.svg"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert 'width="1600"' in text
        assert 'font-size="40"' in text
        assert "95%" in text
        assert "summary " in text


def test_scenario_visual_is_grounded_in_the_flagship_configuration(tmp_path: Path) -> None:
    generate_portfolio_visuals(SUMMARY, tmp_path, SCENARIO)
    text = (tmp_path / "scenario-topology.svg").read_text(encoding="utf-8")

    assert 'width="1600"' in text
    assert "3 gNodeBs" in text
    assert "12 UEs" in text
    assert "Broadband UE x 8" in text
    assert "Low-latency UE x 4" in text
    assert "3.5 GHz" in text
    assert "100 MHz" in text
    assert "5 ms deadline" in text


def test_flagship_evidence_plots_use_the_current_visual_system(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    metrics = bundle / "metrics"
    metrics.mkdir(parents=True)
    shutil.copyfile(SUMMARY, metrics / "summary.json")

    manifest = generate_experiment_plots(bundle)
    assert manifest["plot_count"] == 14
    assert (bundle / "plots" / "plot-manifest.json").read_bytes() == (
        COMMITTED_EVIDENCE_PLOTS / "plot-manifest.json"
    ).read_bytes()
    for plot in manifest["plots"]:
        name = plot["path"]
        generated = bundle / "plots" / name
        committed = COMMITTED_EVIDENCE_PLOTS / name
        assert generated.read_bytes() == committed.read_bytes()
        text = generated.read_text(encoding="utf-8")
        assert 'data-design-system="systems-lab-v1"' in text
        assert "#f4f6f8" in text
        assert "Arial Narrow" in text
        assert "<linearGradient" not in text
