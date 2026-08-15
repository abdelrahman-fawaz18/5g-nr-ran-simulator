from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
import yaml

from nr_ran_sim.errors import ModelDomainError
from nr_ran_sim.experiments.seeds import OwnedRng, SemanticRngRegistry
from nr_ran_sim.radio.geometry import Position3D, link_geometry
from nr_ran_sim.radio.propagation import (
    PropagationState,
    Scenario,
    draw_static_shadow_fading_db,
    evaluate_path_loss,
    los_probability,
    select_effective_environment_height_m,
    select_los_state,
)

FC_HZ = 3.5e9
C_MPS = 3.0e8
VECTOR_FILE = Path(__file__).parent / "data" / "tr38901_path_loss_vectors.yaml"


def _geometry(distance_m: float, h_bs: float, h_ut: float):  # type: ignore[no-untyped-def]
    return link_geometry(Position3D(0.0, 0.0, h_bs), Position3D(distance_m, 0.0, h_ut))


def _rma_oracle(distance_m: float, state: PropagationState) -> tuple[float, float, float]:
    h_bs, h_ut, h, width = 35.0, 1.5, 5.0, 20.0
    d_3d = math.hypot(distance_m, h_bs - h_ut)
    frequency_ghz = FC_HZ / 1e9
    breakpoint = 2 * math.pi * h_bs * h_ut * FC_HZ / C_MPS

    def pl1(distance_3d_m: float) -> float:
        return (
            20 * math.log10(40 * math.pi * distance_3d_m * frequency_ghz / 3)
            + min(0.03 * h**1.72, 10) * math.log10(distance_3d_m)
            - min(0.044 * h**1.72, 14.77)
            + 0.002 * math.log10(h) * distance_3d_m
        )

    los = (
        pl1(d_3d)
        if distance_m <= breakpoint
        else pl1(breakpoint) + 40 * math.log10(d_3d / breakpoint)
    )
    candidate = (
        161.04
        - 7.1 * math.log10(width)
        + 7.5 * math.log10(h)
        - (24.37 - 3.7 * (h / h_bs) ** 2) * math.log10(h_bs)
        + (43.42 - 3.1 * math.log10(h_bs)) * (math.log10(d_3d) - 3)
        + 20 * math.log10(frequency_ghz)
        - (3.2 * math.log10(11.75 * h_ut) ** 2 - 4.97)
    )
    expected = los if state == "los" else max(los, candidate)
    return breakpoint, los, expected


def _uma_oracle(distance_m: float, state: PropagationState) -> tuple[float, float, float]:
    h_bs, h_ut, effective = 25.0, 1.5, 1.0
    d_3d = math.hypot(distance_m, h_bs - h_ut)
    frequency_ghz = FC_HZ / 1e9
    breakpoint = 4 * (h_bs - effective) * (h_ut - effective) * FC_HZ / C_MPS
    if distance_m <= breakpoint:
        los = 28 + 22 * math.log10(d_3d) + 20 * math.log10(frequency_ghz)
    else:
        los = (
            28
            + 40 * math.log10(d_3d)
            + 20 * math.log10(frequency_ghz)
            - 9 * math.log10(breakpoint**2 + (h_bs - h_ut) ** 2)
        )
    candidate = (
        13.54 + 39.08 * math.log10(d_3d) + 20 * math.log10(frequency_ghz) - 0.6 * (h_ut - 1.5)
    )
    return breakpoint, los, los if state == "los" else max(los, candidate)


def _umi_oracle(distance_m: float, state: PropagationState) -> tuple[float, float, float]:
    h_bs, h_ut, effective = 10.0, 1.5, 1.0
    d_3d = math.hypot(distance_m, h_bs - h_ut)
    frequency_ghz = FC_HZ / 1e9
    breakpoint = 4 * (h_bs - effective) * (h_ut - effective) * FC_HZ / C_MPS
    if distance_m <= breakpoint:
        los = 32.4 + 21 * math.log10(d_3d) + 20 * math.log10(frequency_ghz)
    else:
        los = (
            32.4
            + 40 * math.log10(d_3d)
            + 20 * math.log10(frequency_ghz)
            - 9.5 * math.log10(breakpoint**2 + (h_bs - h_ut) ** 2)
        )
    candidate = (
        22.4 + 35.3 * math.log10(d_3d) + 21.3 * math.log10(frequency_ghz) - 0.3 * (h_ut - 1.5)
    )
    return breakpoint, los, los if state == "los" else max(los, candidate)


@pytest.mark.parametrize(
    ("scenario", "state", "distance_m", "h_bs", "h_ut", "oracle"),
    [
        ("rma", "los", 10.0, 35.0, 1.5, _rma_oracle),
        ("rma", "los", 1000.0, 35.0, 1.5, _rma_oracle),
        ("rma", "los", 3848.451000647497, 35.0, 1.5, _rma_oracle),
        ("rma", "los", 5000.0, 35.0, 1.5, _rma_oracle),
        ("rma", "los", 10000.0, 35.0, 1.5, _rma_oracle),
        ("rma", "nlos", 10.0, 35.0, 1.5, _rma_oracle),
        ("rma", "nlos", 1000.0, 35.0, 1.5, _rma_oracle),
        ("rma", "nlos", 5000.0, 35.0, 1.5, _rma_oracle),
        ("uma", "los", 10.0, 25.0, 1.5, _uma_oracle),
        ("uma", "los", 100.0, 25.0, 1.5, _uma_oracle),
        ("uma", "los", 560.0, 25.0, 1.5, _uma_oracle),
        ("uma", "los", 1000.0, 25.0, 1.5, _uma_oracle),
        ("uma", "los", 5000.0, 25.0, 1.5, _uma_oracle),
        ("uma", "nlos", 10.0, 25.0, 1.5, _uma_oracle),
        ("uma", "nlos", 100.0, 25.0, 1.5, _uma_oracle),
        ("uma", "nlos", 5000.0, 25.0, 1.5, _uma_oracle),
        ("umi_street_canyon", "los", 10.0, 10.0, 1.5, _umi_oracle),
        ("umi_street_canyon", "los", 100.0, 10.0, 1.5, _umi_oracle),
        ("umi_street_canyon", "los", 210.0, 10.0, 1.5, _umi_oracle),
        ("umi_street_canyon", "los", 1000.0, 10.0, 1.5, _umi_oracle),
        ("umi_street_canyon", "los", 5000.0, 10.0, 1.5, _umi_oracle),
        ("umi_street_canyon", "nlos", 10.0, 10.0, 1.5, _umi_oracle),
        ("umi_street_canyon", "nlos", 100.0, 10.0, 1.5, _umi_oracle),
        ("umi_street_canyon", "nlos", 5000.0, 10.0, 1.5, _umi_oracle),
    ],
)
def test_release18_path_loss_matches_independent_reference_calculation(
    scenario: Scenario,
    state: PropagationState,
    distance_m: float,
    h_bs: float,
    h_ut: float,
    oracle: object,
) -> None:
    calculate = cast(object, oracle)
    assert callable(calculate)
    expected_breakpoint, expected_los, expected = calculate(distance_m, state)
    result = evaluate_path_loss(
        scenario,
        state,
        _geometry(distance_m, h_bs, h_ut),
        FC_HZ,
        effective_environment_height_m=None if scenario == "rma" else 1.0,
        average_building_height_m=5.0 if scenario == "rma" else None,
        average_street_width_m=20.0 if scenario == "rma" else None,
    )
    assert result.breakpoint_distance_m == pytest.approx(expected_breakpoint, abs=1e-9)
    assert result.los_path_loss_db == pytest.approx(expected_los, abs=1e-9)
    assert result.basic_path_loss_db == pytest.approx(expected, abs=1e-9)
    assert result.total_path_loss_db == result.basic_path_loss_db
    assert result.domain_status == "inside"
    assert result.as_dict()["source_location"] == "TR 38.901 V18.1.0 Table 7.4.1-1"
    expected_sigma = (
        {"rma": 8.0, "uma": 6.0, "umi_street_canyon": 7.82}[scenario]
        if state == "nlos"
        else (6.0 if scenario == "rma" and distance_m > expected_breakpoint else 4.0)
    )
    assert result.shadow_standard_deviation_db == expected_sigma
    if state == "nlos":
        assert result.nlos_candidate_path_loss_db is not None
        assert result.basic_path_loss_db >= result.los_path_loss_db


@pytest.mark.parametrize(
    ("scenario", "distance_m", "height_m", "expected"),
    [
        ("rma", 10.0, 1.5, 1.0),
        ("rma", 1010.0, 1.5, math.exp(-1.0)),
        ("umi_street_canyon", 18.0, 1.5, 1.0),
        (
            "umi_street_canyon",
            100.0,
            1.5,
            18 / 100 + math.exp(-100 / 36) * (1 - 18 / 100),
        ),
        ("uma", 18.0, 1.5, 1.0),
        ("uma", 100.0, 1.5, 18 / 100 + math.exp(-100 / 63) * (1 - 18 / 100)),
        (
            "uma",
            100.0,
            22.5,
            (18 / 100 + math.exp(-100 / 63) * (1 - 18 / 100))
            * (1 + ((22.5 - 13) / 10) ** 1.5 * 1.25 * math.exp(-100 / 150)),
        ),
    ],
)
def test_los_probability_matches_table_7421(
    scenario: Scenario,
    distance_m: float,
    height_m: float,
    expected: float,
) -> None:
    assert los_probability(scenario, distance_m, height_m) == pytest.approx(expected, abs=1e-12)


def test_los_selection_explicit_and_seeded_modes_are_observable() -> None:
    explicit = select_los_state(
        "uma",
        100.0,
        1.5,
        mode="explicit",
        explicit_state="nlos",
        rng=None,
    )
    assert explicit.state == "nlos"
    assert explicit.uniform_draw is None
    assert explicit.as_dict()["mode"] == "explicit"

    registry = SemanticRngRegistry("baseline", "0x00000000000000000000000000000001", 0)
    seeded = select_los_state(
        "uma",
        100.0,
        1.5,
        mode="probability_static",
        explicit_state=None,
        rng=registry.acquire("link/a/b/los", owner="test"),
    )
    assert seeded.state in {"los", "nlos"}
    assert seeded.uniform_draw is not None

    with pytest.raises(ModelDomainError, match="supplied"):
        select_los_state("uma", 100.0, 1.5, mode="explicit", explicit_state=None, rng=None)
    with pytest.raises(ModelDomainError, match="owned RNG"):
        select_los_state(
            "uma",
            100.0,
            1.5,
            mode="probability_static",
            explicit_state=None,
            rng=None,
        )


@dataclass
class _ControlledRng:
    draws: list[float]
    integer_result: int = 0

    def standard_uniform(self) -> float:
        return self.draws.pop(0)

    def integer_inclusive(self, minimum: int, maximum: int) -> int:
        assert minimum <= self.integer_result <= maximum
        return self.integer_result


def test_effective_environment_height_follows_note1_and_records_random_choice() -> None:
    assert select_effective_environment_height_m("rma", 100.0, 1.5, rng=None) is None
    assert select_effective_environment_height_m("umi_street_canyon", 100.0, 1.5, rng=None) == 1
    assert select_effective_environment_height_m("uma", 100.0, 12.0, rng=None) == 1

    choose_one = cast(OwnedRng, _ControlledRng([0.0]))
    assert select_effective_environment_height_m("uma", 100.0, 22.5, rng=choose_one) == 1
    choose_discrete = cast(OwnedRng, _ControlledRng([0.999], integer_result=2))
    assert select_effective_environment_height_m("uma", 100.0, 22.5, rng=choose_discrete) == 18
    with pytest.raises(ModelDomainError, match="requires an owned RNG"):
        select_effective_environment_height_m("uma", 100.0, 22.5, rng=None)


@pytest.mark.parametrize(
    ("scenario", "state", "distance", "h_bs", "h_ut", "effective", "building", "street"),
    [
        ("uma", "los", 9.999, 25.0, 1.5, 1.0, None, None),
        ("uma", "los", 5000.001, 25.0, 1.5, 1.0, None, None),
        ("uma", "los", 100.0, 24.0, 1.5, 1.0, None, None),
        ("uma", "los", 100.0, 25.0, 1.4, 1.0, None, None),
        ("umi_street_canyon", "los", 100.0, 10.0, 1.5, 2.0, None, None),
        ("rma", "nlos", 5000.001, 35.0, 1.5, None, 5.0, 20.0),
        ("rma", "los", 100.0, 35.0, 1.5, None, None, 20.0),
        ("rma", "los", 100.0, 35.0, 1.5, None, 4.9, 20.0),
    ],
)
def test_path_loss_rejects_out_of_domain_inputs_without_clipping(
    scenario: Scenario,
    state: PropagationState,
    distance: float,
    h_bs: float,
    h_ut: float,
    effective: float | None,
    building: float | None,
    street: float | None,
) -> None:
    with pytest.raises(ModelDomainError) as raised:
        evaluate_path_loss(
            scenario,
            state,
            _geometry(distance, h_bs, h_ut),
            FC_HZ,
            effective_environment_height_m=effective,
            average_building_height_m=building,
            average_street_width_m=street,
        )
    assert raised.value.context["requirement"] == "PROP-004"


def test_path_loss_rejects_frequency_and_shadow_nonfinite_values() -> None:
    geometry = _geometry(100.0, 25.0, 1.5)
    with pytest.raises(ModelDomainError, match="outside"):
        evaluate_path_loss(
            "uma",
            "los",
            geometry,
            7.126e9,
            effective_environment_height_m=1.0,
            average_building_height_m=None,
            average_street_width_m=None,
        )
    result = evaluate_path_loss(
        "uma",
        "los",
        geometry,
        FC_HZ,
        effective_environment_height_m=1.0,
        average_building_height_m=None,
        average_street_width_m=None,
    )
    shadowed = result.with_shadow(3.25)
    assert shadowed.total_path_loss_db == pytest.approx(result.basic_path_loss_db + 3.25)
    assert draw_static_shadow_fading_db(result, None) == 0.0
    registry = SemanticRngRegistry("baseline", "0x00000000000000000000000000000001", 0)
    drawn = draw_static_shadow_fading_db(
        result,
        registry.acquire("link/a/b/shadow", owner="test"),
    )
    assert math.isfinite(drawn)
    with pytest.raises(ModelDomainError, match="finite"):
        result.with_shadow(math.inf)


def test_path_loss_is_monotonic_with_distance_inside_each_urban_segment() -> None:
    for scenario, h_bs in (("uma", 25.0), ("umi_street_canyon", 10.0)):
        values = [
            evaluate_path_loss(
                cast(Scenario, scenario),
                "los",
                _geometry(distance, h_bs, 1.5),
                FC_HZ,
                effective_environment_height_m=1.0,
                average_building_height_m=None,
                average_street_width_m=None,
            ).basic_path_loss_db
            for distance in (10.0, 20.0, 50.0, 100.0, 200.0, 1000.0, 5000.0)
        ]
        assert values == sorted(values)


@pytest.mark.parametrize(
    ("scenario", "breakpoint", "h_bs", "effective", "building", "street", "tolerance_db"),
    [
        ("rma", 3848.4510006474966, 35.0, None, 5.0, 20.0, 0.001),
        ("uma", 560.0, 25.0, 1.0, None, None, 1e-6),
        ("umi_street_canyon", 210.0, 10.0, 1.0, None, None, 1e-6),
    ],
)
def test_breakpoint_neighbourhood_has_no_material_jump(
    scenario: Scenario,
    breakpoint: float,
    h_bs: float,
    effective: float | None,
    building: float | None,
    street: float | None,
    tolerance_db: float,
) -> None:
    values = [
        evaluate_path_loss(
            scenario,
            "los",
            _geometry(breakpoint + offset, h_bs, 1.5),
            FC_HZ,
            effective_environment_height_m=effective,
            average_building_height_m=building,
            average_street_width_m=street,
        ).basic_path_loss_db
        for offset in (-1e-6, 1e-6)
    ]
    # RMa's source PL2 uses d_BP rather than the 3D distance at d_2D=d_BP, hence its
    # standards-defined sub-millidecibel step is checked with a scenario-specific tolerance.
    assert abs(values[1] - values[0]) < tolerance_db


def test_committed_path_loss_vector_fixture_matches_production() -> None:
    fixture = yaml.safe_load(VECTOR_FILE.read_text(encoding="utf-8"))
    assert fixture["source"]["version"] == "18.1.0"
    tolerance = float(fixture["calculation"]["tolerance_db"])
    for vector in fixture["vectors"]:
        scenario = cast(Scenario, vector["scenario"])
        state = cast(PropagationState, vector["state"])
        h_bs = {"rma": 35.0, "uma": 25.0, "umi_street_canyon": 10.0}[scenario]
        result = evaluate_path_loss(
            scenario,
            state,
            _geometry(float(vector["distance_2d_m"]), h_bs, 1.5),
            FC_HZ,
            effective_environment_height_m=None if scenario == "rma" else 1.0,
            average_building_height_m=5.0 if scenario == "rma" else None,
            average_street_width_m=20.0 if scenario == "rma" else None,
        )
        assert result.basic_path_loss_db == pytest.approx(
            float(vector["expected_path_loss_db"]),
            abs=tolerance,
        ), vector["id"]


def test_static_shadow_generator_has_fixed_seed_gaussian_sanity() -> None:
    registry = SemanticRngRegistry("baseline", "0x33333333333333333333333333333333", 0)
    stream = registry.acquire("link/a/b/shadow-statistical", owner="statistical-test")
    samples = [stream.normal(0.0, 4.0) for _ in range(50_000)]
    # Fixed PCG64DXSM sample; bounds are wider than three standard errors.
    assert abs(statistics.fmean(samples)) < 0.07
    assert statistics.pstdev(samples) == pytest.approx(4.0, abs=0.06)


def test_seeded_los_draw_frequency_matches_probability_with_fixed_sample() -> None:
    expected = los_probability("uma", 100.0, 1.5)
    registry = SemanticRngRegistry("baseline", "0x44444444444444444444444444444444", 0)
    stream = registry.acquire("link/a/b/los-statistical", owner="statistical-test")
    observed = sum(stream.standard_uniform() < expected for _ in range(50_000)) / 50_000
    # Fixed sample; 0.01 is more than four Bernoulli standard errors here.
    assert observed == pytest.approx(expected, abs=0.01)
