from __future__ import annotations

import math

import pytest

from nr_ran_sim.errors import ModelDomainError
from nr_ran_sim.radio.link_adaptation import cqi_threshold_db, select_link_adaptation
from nr_ran_sim.radio.nr_tables import CQI_TABLE_1, MCS_TABLE_1


def test_cqi_thresholds_are_strictly_increasing_and_select_exact_boundaries() -> None:
    thresholds = [cqi_threshold_db(entry, 3.0) for entry in CQI_TABLE_1[1:]]
    assert thresholds == sorted(thresholds)
    for entry, threshold in zip(CQI_TABLE_1[1:], thresholds, strict=True):
        selected = select_link_adaptation(threshold, 3.0)
        assert selected.cqi is not None
        assert selected.cqi.index == entry.index
        assert selected.cqi_threshold_db == pytest.approx(threshold, abs=1e-12)


def test_link_adaptation_has_explicit_outage_and_unsupported_low_cqi_states() -> None:
    first_threshold = cqi_threshold_db(CQI_TABLE_1[1], 3.0)
    outage = select_link_adaptation(math.nextafter(first_threshold, -math.inf), 3.0)
    cqi_one = select_link_adaptation(-5.5, 3.0)
    assert outage.state == "outage_below_cqi1"
    assert outage.cqi is outage.mcs is None
    assert cqi_one.state == "cqi_without_supported_mcs"
    assert cqi_one.cqi is not None
    assert cqi_one.cqi.index == 1
    assert cqi_one.mcs is None


def test_selected_mcs_is_highest_efficiency_not_above_cqi() -> None:
    for cqi in CQI_TABLE_1[2:]:
        threshold = cqi_threshold_db(cqi, 3.0)
        result = select_link_adaptation(threshold, 3.0)
        assert result.cqi == cqi
        assert result.mcs is not None
        eligible = [
            entry for entry in MCS_TABLE_1 if entry.spectral_efficiency <= cqi.spectral_efficiency
        ]
        assert result.mcs == max(
            eligible, key=lambda entry: (entry.spectral_efficiency, entry.index)
        )
        assert result.calibration_state == "project-derived-analytical-uncalibrated"
        assert result.target_transport_block_error_probability == 0.1


def test_selected_cqi_and_mcs_are_monotonic_with_sinr() -> None:
    results = [select_link_adaptation(value / 10, 3.0) for value in range(-100, 301)]
    cqi_indices = [-1 if result.cqi is None else result.cqi.index for result in results]
    mcs_indices = [-1 if result.mcs is None else result.mcs.index for result in results]
    assert cqi_indices == sorted(cqi_indices)
    assert mcs_indices == sorted(mcs_indices)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_link_adaptation_rejects_nonfinite_inputs(value: float) -> None:
    with pytest.raises(ModelDomainError):
        select_link_adaptation(value, 3.0)
    with pytest.raises(ModelDomainError):
        select_link_adaptation(3.0, value)
    with pytest.raises(ModelDomainError):
        cqi_threshold_db(CQI_TABLE_1[1], value)


def test_out_of_range_cqi_has_no_threshold() -> None:
    with pytest.raises(ModelDomainError):
        cqi_threshold_db(CQI_TABLE_1[0], 3.0)
