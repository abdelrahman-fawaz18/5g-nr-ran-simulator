from __future__ import annotations

import math
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nr_ran_sim.config import load_scenario, normalize_scenario
from nr_ran_sim.mac.models import SchedulerObservation, SchedulingCandidate, validate_decision
from nr_ran_sim.mac.policies import (
    MaxCiScheduler,
    ProportionalFairScheduler,
    RoundRobinScheduler,
)
from nr_ran_sim.radio.capacity import evaluate_capacity
from nr_ran_sim.radio.geometry import Position3D, link_geometry
from nr_ran_sim.radio.link import dbm_to_watt, thermal_noise, watt_to_dbm

ROOT = Path(__file__).parents[2]
STATIC_SCENARIO = normalize_scenario(
    load_scenario(ROOT / "examples" / "scenarios" / "scheduler-qos-smoke.yaml")
)
FINITE_COORDINATE = st.floats(
    min_value=-1_000_000,
    max_value=1_000_000,
    allow_nan=False,
    allow_infinity=False,
    width=64,
)


@pytest.mark.property
@given(
    x1=FINITE_COORDINATE,
    y1=FINITE_COORDINATE,
    z1=FINITE_COORDINATE,
    x2=FINITE_COORDINATE,
    y2=FINITE_COORDINATE,
    z2=FINITE_COORDINATE,
)
def test_geometry_is_symmetric_and_never_has_direct_distance_below_horizontal(
    x1: float,
    y1: float,
    z1: float,
    x2: float,
    y2: float,
    z2: float,
) -> None:
    forward = link_geometry(Position3D(x1, y1, z1), Position3D(x2, y2, z2))
    reverse = link_geometry(Position3D(x2, y2, z2), Position3D(x1, y1, z1))

    assert forward.horizontal_distance_m == reverse.horizontal_distance_m
    assert forward.direct_distance_m == reverse.direct_distance_m
    assert forward.direct_distance_m >= forward.horizontal_distance_m
    assert math.isfinite(forward.direct_distance_m)


@pytest.mark.property
@given(
    power_dbm=st.floats(
        min_value=-200,
        max_value=100,
        allow_nan=False,
        allow_infinity=False,
        width=64,
    ),
    increase_db=st.floats(
        min_value=0,
        max_value=60,
        allow_nan=False,
        allow_infinity=False,
        width=64,
    ),
)
def test_power_conversion_round_trips_and_increasing_tx_power_cannot_reduce_linear_power(
    power_dbm: float,
    increase_db: float,
) -> None:
    baseline_w = dbm_to_watt(power_dbm)
    increased_w = dbm_to_watt(power_dbm + increase_db)

    assert watt_to_dbm(baseline_w) == pytest.approx(power_dbm, abs=1e-12)
    assert increased_w >= baseline_w


@pytest.mark.property
@given(
    bandwidth_hz=st.integers(min_value=1, max_value=400_000_000),
    bandwidth_multiplier=st.integers(min_value=1, max_value=8),
    noise_figure_db=st.floats(
        min_value=0,
        max_value=30,
        allow_nan=False,
        allow_infinity=False,
        width=32,
    ),
    added_noise_figure_db=st.floats(
        min_value=0,
        max_value=20,
        allow_nan=False,
        allow_infinity=False,
        width=32,
    ),
)
def test_thermal_noise_is_monotonic_in_bandwidth_and_noise_figure(
    bandwidth_hz: int,
    bandwidth_multiplier: int,
    noise_figure_db: float,
    added_noise_figure_db: float,
) -> None:
    baseline = thermal_noise(bandwidth_hz, noise_figure_db)
    wider = thermal_noise(bandwidth_hz * bandwidth_multiplier, noise_figure_db)
    noisier = thermal_noise(bandwidth_hz, noise_figure_db + added_noise_figure_db)

    assert wider.noise_power_w >= baseline.noise_power_w
    assert noisier.noise_power_w >= baseline.noise_power_w


@pytest.mark.property
@given(
    sinr_db=st.floats(
        min_value=-20,
        max_value=45,
        allow_nan=False,
        allow_infinity=False,
        width=32,
    ),
    added_loss_db=st.floats(
        min_value=0,
        max_value=40,
        allow_nan=False,
        allow_infinity=False,
        width=32,
    ),
    allocated_prbs=st.integers(min_value=0, max_value=273),
)
def test_capacity_cannot_increase_when_link_loss_increases(
    sinr_db: float,
    added_loss_db: float,
    allocated_prbs: int,
) -> None:
    baseline = evaluate_capacity(
        STATIC_SCENARIO.radio,
        sinr_db=sinr_db,
        allocated_prbs=allocated_prbs,
    )
    degraded = evaluate_capacity(
        STATIC_SCENARIO.radio,
        sinr_db=sinr_db - added_loss_db,
        allocated_prbs=allocated_prbs,
    )

    assert degraded.capacity_bits_per_interval <= baseline.capacity_bits_per_interval


@pytest.mark.property
@given(
    sinr_db=st.floats(
        min_value=-20,
        max_value=45,
        allow_nan=False,
        allow_infinity=False,
        width=32,
    ),
    lower_prbs=st.integers(min_value=0, max_value=273),
    added_prbs=st.integers(min_value=0, max_value=273),
)
def test_capacity_cannot_decrease_when_prbs_are_added(
    sinr_db: float,
    lower_prbs: int,
    added_prbs: int,
) -> None:
    upper_prbs = min(273, lower_prbs + added_prbs)
    lower = evaluate_capacity(
        STATIC_SCENARIO.radio,
        sinr_db=sinr_db,
        allocated_prbs=lower_prbs,
    )
    upper = evaluate_capacity(
        STATIC_SCENARIO.radio,
        sinr_db=sinr_db,
        allocated_prbs=upper_prbs,
    )

    assert upper.capacity_bits_per_interval >= lower.capacity_bits_per_interval


@pytest.mark.property
@given(
    available_prbs=st.integers(min_value=1, max_value=275),
    achievable_payloads=st.lists(
        st.integers(min_value=0, max_value=5_000_000),
        min_size=0,
        max_size=12,
    ),
)
def test_every_baseline_scheduler_preserves_the_common_allocation_contract(
    available_prbs: int,
    achievable_payloads: list[int],
) -> None:
    candidates = tuple(
        SchedulingCandidate(
            ue_id=f"ue/{ordinal:03d}",
            queue_payload_bits=1_000_000,
            achievable_payload_bits=payload,
            achievable_rate_bps=payload * 2_000,
            sinr_db=float(ordinal),
        )
        for ordinal, payload in enumerate(achievable_payloads)
    )
    observation = SchedulerObservation(
        tick=0,
        interval_ns=500_000,
        cell_id="cell/property",
        available_prbs=available_prbs,
        candidates=candidates,
    )
    policies = (
        RoundRobinScheduler(),
        MaxCiScheduler(),
        ProportionalFairScheduler(Decimal("0.1"), Decimal("1000")),
    )

    for policy in policies:
        decision = policy.decide(observation)
        validate_decision(observation, decision)
        assert sum(allocation.prbs for allocation in decision.allocations) <= available_prbs
        assert all(allocation.prbs > 0 for allocation in decision.allocations)
