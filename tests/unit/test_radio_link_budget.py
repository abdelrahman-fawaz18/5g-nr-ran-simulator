from __future__ import annotations

import math
from dataclasses import replace

import pytest

from nr_ran_sim.errors import ModelDomainError
from nr_ran_sim.radio.geometry import Position3D, link_geometry
from nr_ran_sim.radio.link import (
    InterferenceResult,
    aggregate_interference,
    calculate_link_budget,
    calculate_sinr,
    dbm_to_watt,
    thermal_noise,
    watt_to_dbm,
)
from nr_ran_sim.radio.propagation import evaluate_path_loss
from nr_ran_sim.radio.topology import RadioCell, RadioUe


def _cell(*, cell_id: str = "cell/a", misc_loss_db: float = 2.0) -> RadioCell:
    return RadioCell(
        id=cell_id,
        configuration_id=cell_id.removeprefix("cell/"),
        position=Position3D(0.0, 0.0, 25.0),
        transmit_power_w=dbm_to_watt(46.0),
        transmit_power_dbm=46.0,
        antenna_gain_dbi=15.0,
        miscellaneous_loss_db=misc_loss_db,
    )


def _ue() -> RadioUe:
    return RadioUe(
        id="ue/users/000000",
        group_id="users",
        ordinal=0,
        position=Position3D(100.0, 0.0, 1.5),
        receiver_noise_figure_db=7.0,
        antenna_gain_dbi=0.0,
        penetration_loss_db=0.0,
        placement_attempts=0,
    )


def _path_loss_130():  # type: ignore[no-untyped-def]
    evaluated = evaluate_path_loss(
        "uma",
        "los",
        link_geometry(_cell().position, _ue().position),
        3.5e9,
        effective_environment_height_m=1.0,
        average_building_height_m=None,
        average_street_width_m=None,
    )
    return replace(
        evaluated,
        basic_path_loss_db=130.0,
        shadow_fading_db=0.0,
        total_path_loss_db=130.0,
    )


def _budget(*, cell_id: str = "cell/a", received_dbm: float = -71.0):  # type: ignore[no-untyped-def]
    budget = calculate_link_budget(
        _cell(cell_id=cell_id),
        _ue(),
        _path_loss_130(),
        transmission_bandwidth_hz=20_000_000,
        subcarrier_spacing_hz=15_000,
    )
    received_w = dbm_to_watt(received_dbm)
    return replace(
        budget,
        received_power_dbm=received_dbm,
        received_power_w=received_w,
        received_psd_dbm_per_hz=received_dbm - 10 * math.log10(20_000_000),
        received_psd_w_per_hz=received_w / 20_000_000,
        reference_signal_received_power_dbm=(
            received_dbm - 10 * math.log10(20_000_000) + 10 * math.log10(15_000)
        ),
        reference_signal_received_power_w=received_w / 20_000_000 * 15_000,
    )


def test_hand_calculated_link_budget_exports_every_term() -> None:
    result = calculate_link_budget(
        _cell(),
        _ue(),
        _path_loss_130(),
        transmission_bandwidth_hz=20_000_000,
        subcarrier_spacing_hz=15_000,
    )
    assert result.received_power_dbm == pytest.approx(-71.0, abs=1e-12)
    assert watt_to_dbm(result.received_power_w) == pytest.approx(-71.0, abs=1e-12)
    assert result.total_link_loss_db == 132.0
    assert result.transmit_psd_w_per_hz * result.transmission_bandwidth_hz == pytest.approx(
        result.transmit_power_w
    )
    assert result.received_psd_w_per_hz * result.transmission_bandwidth_hz == pytest.approx(
        result.received_power_w
    )
    assert result.reference_signal_received_power_w == pytest.approx(
        result.received_psd_w_per_hz * result.subcarrier_spacing_hz
    )
    exported = result.as_dict()
    assert exported["basic_path_loss_db"] == 130.0
    assert exported["miscellaneous_loss_db"] == 2.0


@pytest.mark.parametrize(
    ("bandwidth_hz", "expected_dbm"),
    [(20_000_000, -93.98970004336019), (100_000_000, -87.0)],
)
def test_thermal_noise_reference_vectors(bandwidth_hz: int, expected_dbm: float) -> None:
    result = thermal_noise(bandwidth_hz, 7.0)
    assert result.noise_power_dbm == pytest.approx(expected_dbm, abs=1e-9)
    assert watt_to_dbm(result.noise_power_w) == pytest.approx(expected_dbm, abs=1e-9)
    assert result.as_dict()["density_dbm_per_hz"] == -174.0


def test_interference_is_summed_in_linear_power() -> None:
    serving = _budget(cell_id="cell/a", received_dbm=-80.0)
    interferer_b = _budget(cell_id="cell/b", received_dbm=-90.0)
    interferer_c = _budget(cell_id="cell/c", received_dbm=-90.0)
    result = aggregate_interference(
        "full_buffer_reuse1-v1",
        "cell/a",
        (interferer_c, serving, interferer_b),
    )
    assert result.total_power_dbm == pytest.approx(-86.98970004336019, abs=1e-9)
    assert [component.cell_id for component in result.components] == ["cell/b", "cell/c"]
    assert result.as_dict()["profile_id"] == "full_buffer_reuse1-v1"

    noise_limited = aggregate_interference("noise_limited-v1", "cell/a", (serving,))
    assert noise_limited.total_power_w == 0.0
    assert noise_limited.total_power_dbm is None
    assert noise_limited.components == ()


def test_sinr_reference_vector_is_reconstructable() -> None:
    signal = _budget(received_dbm=-80.0)
    noise = replace(
        thermal_noise(100_000_000, 7.0),
        noise_power_dbm=-100.0,
        noise_power_w=dbm_to_watt(-100.0),
    )
    interference = InterferenceResult(
        profile_id="full_buffer_reuse1-v1",
        components=(),
        total_power_w=dbm_to_watt(-90.0),
        total_power_dbm=-90.0,
    )
    result = calculate_sinr(signal, noise, interference)
    expected_linear = 1e-11 / (1e-12 + 1e-13)
    assert result.sinr_linear == pytest.approx(expected_linear, rel=1e-12)
    assert result.sinr_db == pytest.approx(9.58607314841775, abs=1e-9)
    assert result.denominator_power_w == pytest.approx(
        result.interference_power_w + result.noise_power_w
    )
    assert result.as_dict()["signal_power_dbm"] == -80.0


@pytest.mark.parametrize(
    "operation",
    [
        lambda: dbm_to_watt(math.inf),
        lambda: watt_to_dbm(0.0),
        lambda: thermal_noise(0, 7.0),
        lambda: thermal_noise(20_000_000, -1.0),
        lambda: calculate_link_budget(
            _cell(), _ue(), _path_loss_130(), transmission_bandwidth_hz=0, subcarrier_spacing_hz=1
        ),
    ],
)
def test_invalid_link_arithmetic_fails_closed(operation: object) -> None:
    assert callable(operation)
    with pytest.raises(ModelDomainError):
        operation()


def test_sinr_rejects_nonpositive_denominator() -> None:
    noise = replace(thermal_noise(1, 0.0), noise_power_w=0.0, noise_power_dbm=-math.inf)
    interference = InterferenceResult(
        profile_id="noise_limited-v1",
        components=(),
        total_power_w=0.0,
        total_power_dbm=None,
    )
    with pytest.raises(ModelDomainError, match="denominator"):
        calculate_sinr(_budget(), noise, interference)
