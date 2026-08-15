from __future__ import annotations

from typing import Any

import pytest

from nr_ran_sim.config.models import ScenarioConfig
from nr_ran_sim.config.normalize import normalize_scenario
from nr_ran_sim.errors import ModelDomainError
from nr_ran_sim.radio.capacity import evaluate_capacity
from nr_ran_sim.radio.resources import build_resource_grid


def _radio(data: dict[str, Any]):  # type: ignore[no-untyped-def]
    return normalize_scenario(ScenarioConfig.model_validate(data)).radio


@pytest.mark.parametrize(
    ("scs_hz", "expected_numerology", "expected_slots", "expected_duration_ns"),
    [(15_000, 0, 1, 1_000_000), (30_000, 1, 2, 500_000), (60_000, 2, 4, 250_000)],
)
def test_resource_grid_exposes_normal_cp_slot_accounting(
    scenario_data: dict[str, Any],
    scs_hz: int,
    expected_numerology: int,
    expected_slots: int,
    expected_duration_ns: int,
) -> None:
    scenario_data["radio"]["subcarrier_spacing"] = {"value": scs_hz, "unit": "Hz"}
    scenario_data["radio"]["channel_bandwidth"] = {
        "value": 10 if scs_hz == 60_000 else 5,
        "unit": "MHz",
    }
    grid = build_resource_grid(_radio(scenario_data))
    assert grid.numerology == expected_numerology
    assert grid.subcarriers_per_prb == 12
    assert grid.symbols_per_slot == 14
    assert grid.slots_per_ms == expected_slots
    assert grid.slot_duration_ns == expected_duration_ns
    assert grid.scheduling_interval_ns == expected_duration_ns


def test_resource_grid_makes_overhead_rounding_and_tbs_cap_explicit(
    scenario_data: dict[str, Any],
) -> None:
    scenario_data["radio"]["data_re_overhead_fraction"] = 0.14
    grid = build_resource_grid(_radio(scenario_data))
    assert grid.gross_re_per_prb == 168
    assert grid.configured_overhead_fraction == "0.14"
    assert grid.uncapped_data_re_per_prb == 144
    assert grid.tbs_data_re_per_prb == 144
    assert not grid.tbs_cap_applied

    scenario_data["radio"]["data_re_overhead_fraction"] = 0
    uncapped = build_resource_grid(_radio(scenario_data))
    assert uncapped.uncapped_data_re_per_prb == 168
    assert uncapped.tbs_data_re_per_prb == 156
    assert uncapped.tbs_cap_applied


def test_capacity_states_are_explicit_and_never_invent_service(
    scenario_data: dict[str, Any],
) -> None:
    radio = _radio(scenario_data)
    zero = evaluate_capacity(radio, sinr_db=20.0, allocated_prbs=0)
    outage = evaluate_capacity(radio, sinr_db=-20.0, allocated_prbs=radio.prb_count)
    unsupported_cqi = evaluate_capacity(radio, sinr_db=-5.5, allocated_prbs=radio.prb_count)
    available = evaluate_capacity(radio, sinr_db=10.0, allocated_prbs=radio.prb_count)

    assert zero.state == "zero_resource"
    assert zero.capacity_bits_per_interval == zero.capacity_bit_rate_bps == 0
    assert outage.state == "outage_below_cqi1"
    assert unsupported_cqi.state == "cqi_without_supported_mcs"
    assert available.state == "capacity_available"
    assert available.transport_block is not None
    assert available.capacity_bits_per_interval == available.transport_block.transport_block_bits
    assert available.capacity_bit_rate_bps == (
        available.capacity_bits_per_interval * 1_000_000_000 // radio.slot_duration_ns
    )
    assert available.adaptation.error_model == "target-metadata-only-no-bler-sampling-or-harq"


@pytest.mark.parametrize("allocated_prbs", [-1, 274])
def test_capacity_rejects_allocations_outside_cell_grid(
    scenario_data: dict[str, Any], allocated_prbs: int
) -> None:
    radio = _radio(scenario_data)
    with pytest.raises(ModelDomainError) as raised:
        evaluate_capacity(radio, sinr_db=10.0, allocated_prbs=allocated_prbs)
    assert raised.value.context["requirement"] == "LINK-009"
