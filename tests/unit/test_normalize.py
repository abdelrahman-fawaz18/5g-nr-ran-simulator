from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from nr_ran_sim.config.models import ScenarioConfig
from nr_ran_sim.config.normalize import normalize_scenario
from nr_ran_sim.errors import ConfigurationValidationError

EXPECTED_FR1_PRBS = {
    15_000: {
        3: 15,
        5: 25,
        10: 52,
        15: 79,
        20: 106,
        25: 133,
        30: 160,
        35: 188,
        40: 216,
        45: 242,
        50: 270,
    },
    30_000: {
        5: 11,
        10: 24,
        15: 38,
        20: 51,
        25: 65,
        30: 78,
        35: 92,
        40: 106,
        45: 119,
        50: 133,
        60: 162,
        70: 189,
        80: 217,
        90: 245,
        100: 273,
    },
    60_000: {
        10: 11,
        15: 18,
        20: 24,
        25: 31,
        30: 38,
        35: 44,
        40: 51,
        45: 58,
        50: 65,
        60: 79,
        70: 93,
        80: 107,
        90: 121,
        100: 135,
    },
}


def _normalize(data: dict[str, Any]) -> Any:
    return normalize_scenario(ScenarioConfig.model_validate(data))


def test_foundation_scenario_normalizes_to_explicit_runtime_values(
    scenario_data: dict[str, Any],
) -> None:
    normalized = _normalize(scenario_data)
    assert normalized.simulation.stop_ns == 1_400_000_000
    assert normalized.radio.carrier_frequency_hz == Decimal("3500000000")
    assert normalized.radio.prb_count == 273
    assert normalized.radio.numerology == 1
    assert normalized.radio.slot_duration_ns == 500_000
    assert normalized.radio.transmission_bandwidth_hz == 98_280_000
    assert normalized.topology.cells["cell-a"].transmit_power_dbm == Decimal("46")
    assert normalized.topology.ue_groups["users"].penetration_loss_db == Decimal("0")
    assert normalized.traffic_profiles["broadband"].queue.max_payload_bits == 12_000_000
    assert normalized.scheduler.initial_rate_floor_bps == Decimal("1000")
    assert normalized.warnings == ()


@pytest.mark.parametrize(
    ("scs_hz", "bandwidth_mhz", "expected_prbs"),
    [
        (scs_hz, bandwidth_mhz, prbs)
        for scs_hz, bandwidths in EXPECTED_FR1_PRBS.items()
        for bandwidth_mhz, prbs in bandwidths.items()
    ],
)
def test_every_supported_fr1_resource_configuration_resolves(
    scenario_data: dict[str, Any],
    scs_hz: int,
    bandwidth_mhz: int,
    expected_prbs: int,
) -> None:
    scenario_data["radio"]["subcarrier_spacing"] = {"value": scs_hz, "unit": "Hz"}
    scenario_data["radio"]["channel_bandwidth"] = {
        "value": bandwidth_mhz,
        "unit": "MHz",
    }
    radio = _normalize(scenario_data).radio
    assert radio.prb_count == expected_prbs
    assert radio.transmission_bandwidth_hz == expected_prbs * 12 * scs_hz
    assert radio.slot_duration_ns == {15_000: 1_000_000, 30_000: 500_000, 60_000: 250_000}[scs_hz]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("carrier_frequency", {"value": 7.2, "unit": "GHz"}),
        ("channel_bandwidth", {"value": 100, "unit": "MHz"}),
    ],
)
def test_radio_domain_rejection(
    scenario_data: dict[str, Any],
    field: str,
    value: dict[str, Any],
) -> None:
    scenario_data["radio"][field] = value
    if field == "channel_bandwidth":
        scenario_data["radio"]["subcarrier_spacing"] = {"value": 15, "unit": "kHz"}
    with pytest.raises(ConfigurationValidationError) as raised:
        _normalize(scenario_data)
    assert raised.value.context["requirement"] == "CFG-007"


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("simulation", "measurement"), {"value": 0, "unit": "ms"}),
        (("simulation", "warmup"), {"value": -1, "unit": "ms"}),
        (("topology", "cells", "cell-a", "position", "z"), {"value": 0, "unit": "m"}),
        (
            ("topology", "cells", "cell-a", "miscellaneous_loss"),
            {"value": -1, "unit": "dB"},
        ),
        (
            ("topology", "ue_groups", "users", "receiver_noise_figure"),
            {"value": -1, "unit": "dB"},
        ),
        (
            ("topology", "ue_groups", "users", "penetration_loss"),
            {"value": -1, "unit": "dB"},
        ),
    ],
)
def test_nonpositive_semantic_values_fail(
    scenario_data: dict[str, Any],
    path: tuple[str, ...],
    replacement: Any,
) -> None:
    node: dict[str, Any] = scenario_data
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = replacement
    with pytest.raises(ConfigurationValidationError):
        _normalize(scenario_data)


def test_topology_bounds_must_be_ordered(scenario_data: dict[str, Any]) -> None:
    placement = scenario_data["topology"]["ue_groups"]["users"]["placement"]
    placement["x_min"] = {"value": 501, "unit": "m"}
    with pytest.raises(ConfigurationValidationError, match="bounds"):
        _normalize(scenario_data)


def test_periodic_and_uniform_traffic_are_normalized(scenario_data: dict[str, Any]) -> None:
    profile = scenario_data["traffic_profiles"]["broadband"]
    profile["source"] = {
        "type": "bounded_uniform",
        "minimum_interarrival": {"value": 1, "unit": "ms"},
        "maximum_interarrival": {"value": 3, "unit": "ms"},
    }
    profile["packet_size"] = {
        "type": "discrete_uniform",
        "minimum_payload": {"value": 1, "unit": "kbit"},
        "maximum_payload": {"value": 2, "unit": "kbit"},
    }
    normalized = _normalize(scenario_data).traffic_profiles["broadband"]
    assert normalized.source.parameters_ns == {
        "minimum_interarrival": 1_000_000,
        "maximum_interarrival": 3_000_000,
    }
    assert normalized.packet_size.parameters_bits == {
        "minimum_payload": 1000,
        "maximum_payload": 2000,
    }

    profile["source"] = {
        "type": "periodic",
        "interval": {"value": 2, "unit": "ms"},
    }
    periodic = _normalize(scenario_data).traffic_profiles["broadband"].source
    assert periodic.parameters_ns == {"interval": 2_000_000, "initial_offset": 0}


@pytest.mark.parametrize("dimension", ["source", "packet_size"])
def test_reversed_distribution_bounds_fail(
    scenario_data: dict[str, Any],
    dimension: str,
) -> None:
    profile = scenario_data["traffic_profiles"]["broadband"]
    if dimension == "source":
        profile["source"] = {
            "type": "bounded_uniform",
            "minimum_interarrival": {"value": 3, "unit": "ms"},
            "maximum_interarrival": {"value": 1, "unit": "ms"},
        }
    else:
        profile["packet_size"] = {
            "type": "discrete_uniform",
            "minimum_payload": {"value": 3, "unit": "kbit"},
            "maximum_payload": {"value": 1, "unit": "kbit"},
        }
    with pytest.raises(ConfigurationValidationError, match="bounds are reversed"):
        _normalize(scenario_data)


def test_short_drain_emits_structured_warning(scenario_data: dict[str, Any]) -> None:
    scenario_data["simulation"]["drain"] = {"value": 10, "unit": "ms"}
    scenario_data["traffic_profiles"]["broadband"]["deadline"] = {
        "value": 20,
        "unit": "ms",
    }
    warning = _normalize(scenario_data).warnings[0]
    assert warning.code == "drain_shorter_than_maximum_deadline"
    assert warning.requirement == "KPI-002"


@pytest.mark.parametrize(
    "extensions",
    [
        {"not-namespaced": {}},
        {"research.secret": "value"},
        {"research.path": {"dataset": "C:\\machine\\data.csv"}},
    ],
)
def test_extensions_are_namespaced_and_machine_independent(
    scenario_data: dict[str, Any],
    extensions: dict[str, Any],
) -> None:
    scenario_data["extensions"] = extensions
    with pytest.raises(ConfigurationValidationError):
        _normalize(scenario_data)


def test_valid_extension_is_retained(scenario_data: dict[str, Any]) -> None:
    scenario_data["extensions"] = {"research.example": {"label": "sensitivity"}}
    assert _normalize(scenario_data).extensions == scenario_data["extensions"]
