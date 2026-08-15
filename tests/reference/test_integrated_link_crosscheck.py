from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml
from tests.reference.independent_link_oracle import evaluate_integrated_link

from nr_ran_sim.radio.link import (
    LinkBudgetResult,
    aggregate_interference,
    calculate_link_budget,
    calculate_sinr,
    dbm_to_watt,
    thermal_noise,
)
from nr_ran_sim.radio.propagation import PathLossResult
from nr_ran_sim.radio.topology import RadioCell, RadioUe

VECTOR = Path(__file__).parent / "data" / "integrated_link_vector.yaml"


def _production_link(common: dict[str, Any], link: dict[str, Any]) -> LinkBudgetResult:
    cell = cast(
        RadioCell,
        SimpleNamespace(
            id=link["cell_id"],
            transmit_power_w=dbm_to_watt(float(link["transmit_power_dbm"])),
            transmit_power_dbm=float(link["transmit_power_dbm"]),
            antenna_gain_dbi=float(link["transmitter_gain_dbi"]),
            miscellaneous_loss_db=float(common["miscellaneous_loss_db"]),
        ),
    )
    ue = cast(
        RadioUe,
        SimpleNamespace(
            id="ue/reference",
            antenna_gain_dbi=float(common["receiver_gain_dbi"]),
            penetration_loss_db=float(common["penetration_loss_db"]),
        ),
    )
    path_loss = cast(
        PathLossResult,
        SimpleNamespace(
            basic_path_loss_db=float(link["basic_path_loss_db"]),
            shadow_fading_db=float(common["shadow_fading_db"]),
        ),
    )
    return calculate_link_budget(
        cell,
        ue,
        path_loss,
        transmission_bandwidth_hz=common["transmission_bandwidth_hz"],
        subcarrier_spacing_hz=common["subcarrier_spacing_hz"],
    )


@pytest.mark.reference
def test_representative_link_chain_matches_independent_decimal_oracle() -> None:
    vector = yaml.safe_load(VECTOR.read_text(encoding="utf-8"))
    inputs = vector["inputs"]
    expected = vector["expected"]
    oracle = evaluate_integrated_link(inputs)
    db_tolerance = float(vector["tolerances"]["db_absolute"])
    linear_tolerance = float(vector["tolerances"]["linear_relative"])

    for field, value in expected.items():
        assert float(oracle[field]) == pytest.approx(float(value), rel=linear_tolerance, abs=1e-40)

    links = tuple(_production_link(inputs, link) for link in inputs["links"])
    noise = thermal_noise(
        inputs["transmission_bandwidth_hz"],
        float(inputs["receiver_noise_figure_db"]),
    )
    interference = aggregate_interference("full_buffer_reuse1-v1", "cell/serving", links)
    sinr = calculate_sinr(links[0], noise, interference)

    assert links[0].received_power_dbm == pytest.approx(
        float(oracle["serving_received_power_dbm"]), abs=db_tolerance
    )
    assert noise.noise_power_dbm == pytest.approx(
        float(oracle["noise_power_dbm"]), abs=db_tolerance
    )
    assert interference.total_power_w == pytest.approx(
        float(oracle["interference_power_w"]), rel=linear_tolerance
    )
    assert interference.total_power_dbm == pytest.approx(
        float(oracle["interference_power_dbm"]), abs=db_tolerance
    )
    assert sinr.sinr_linear == pytest.approx(float(oracle["sinr_linear"]), rel=linear_tolerance)
    assert sinr.sinr_db == pytest.approx(float(oracle["sinr_db"]), abs=db_tolerance)
