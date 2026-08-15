"""Transparent analytical SINR-to-CQI/MCS link-adaptation abstraction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast

from nr_ran_sim.errors import ModelDomainError
from nr_ran_sim.radio.nr_tables import CQI_TABLE_1, MCS_TABLE_1, CqiTableEntry, McsTableEntry

LINK_ADAPTATION_PROFILE_ID = "analytical-awgn-gap-v1"
TARGET_TRANSPORT_BLOCK_ERROR_PROBABILITY = 0.1


@dataclass(frozen=True, slots=True)
class LinkAdaptationResult:
    profile_id: str
    calibration_state: str
    sinr_db: float
    sinr_linear: float
    implementation_margin_db: float
    implementation_margin_linear: float
    achievable_efficiency_cap: float
    state: Literal["outage_below_cqi1", "cqi_without_supported_mcs", "selected"]
    cqi: CqiTableEntry | None
    cqi_threshold_db: float | None
    mcs: McsTableEntry | None
    target_transport_block_error_probability: float
    error_model: str

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "calibration_state": self.calibration_state,
            "sinr_db": self.sinr_db,
            "sinr_linear": self.sinr_linear,
            "implementation_margin_db": self.implementation_margin_db,
            "implementation_margin_linear": self.implementation_margin_linear,
            "achievable_efficiency_cap": self.achievable_efficiency_cap,
            "state": self.state,
            "cqi": None if self.cqi is None else self.cqi.as_dict(),
            "cqi_threshold_db": self.cqi_threshold_db,
            "mcs": None if self.mcs is None else self.mcs.as_dict(),
            "target_transport_block_error_probability": (
                self.target_transport_block_error_probability
            ),
            "error_model": self.error_model,
        }


def cqi_threshold_db(entry: CqiTableEntry, implementation_margin_db: float) -> float:
    """Return the project-derived AWGN-gap threshold for one in-range CQI row."""

    _finite("implementation_margin_db", implementation_margin_db)
    if entry.spectral_efficiency is None:
        raise ModelDomainError(
            "out-of-range CQI has no analytical threshold",
            {"cqi_index": entry.index, "requirement": "LINK-010"},
        )
    efficiency = float(entry.spectral_efficiency)
    return 10.0 * math.log10(math.pow(2.0, efficiency) - 1.0) + implementation_margin_db


def select_link_adaptation(
    sinr_db: float,
    implementation_margin_db: float,
) -> LinkAdaptationResult:
    """Select CQI then MCS without inventing a calibrated BLER curve."""

    _finite("sinr_db", sinr_db)
    _finite("implementation_margin_db", implementation_margin_db)
    sinr_linear = math.pow(10.0, sinr_db / 10.0)
    margin_linear = math.pow(10.0, implementation_margin_db / 10.0)
    efficiency_cap = math.log2(1.0 + sinr_linear / margin_linear)
    selected_cqi = next(
        (
            entry
            for entry in reversed(CQI_TABLE_1[1:])
            if cqi_threshold_db(entry, implementation_margin_db) <= sinr_db
        ),
        None,
    )
    if selected_cqi is None:
        return _result(
            sinr_db,
            sinr_linear,
            implementation_margin_db,
            margin_linear,
            efficiency_cap,
            "outage_below_cqi1",
            None,
            None,
        )
    cqi_efficiency = cast(Decimal, selected_cqi.spectral_efficiency)
    eligible_mcs = tuple(
        entry for entry in MCS_TABLE_1 if entry.spectral_efficiency <= cqi_efficiency
    )
    selected_mcs = max(
        eligible_mcs,
        key=lambda entry: (entry.spectral_efficiency, entry.index),
        default=None,
    )
    return _result(
        sinr_db,
        sinr_linear,
        implementation_margin_db,
        margin_linear,
        efficiency_cap,
        "cqi_without_supported_mcs" if selected_mcs is None else "selected",
        selected_cqi,
        selected_mcs,
    )


def _result(
    sinr_db: float,
    sinr_linear: float,
    margin_db: float,
    margin_linear: float,
    efficiency_cap: float,
    state: Literal["outage_below_cqi1", "cqi_without_supported_mcs", "selected"],
    cqi: CqiTableEntry | None,
    mcs: McsTableEntry | None,
) -> LinkAdaptationResult:
    return LinkAdaptationResult(
        profile_id=LINK_ADAPTATION_PROFILE_ID,
        calibration_state="project-derived-analytical-uncalibrated",
        sinr_db=sinr_db,
        sinr_linear=sinr_linear,
        implementation_margin_db=margin_db,
        implementation_margin_linear=margin_linear,
        achievable_efficiency_cap=efficiency_cap,
        state=state,
        cqi=cqi,
        cqi_threshold_db=None if cqi is None else cqi_threshold_db(cqi, margin_db),
        mcs=mcs,
        target_transport_block_error_probability=TARGET_TRANSPORT_BLOCK_ERROR_PROBABILITY,
        error_model="target-metadata-only-no-bler-sampling-or-harq",
    )


def _finite(field: str, value: float) -> None:
    if not math.isfinite(value):
        raise ModelDomainError(
            f"{field} must be finite",
            {"field": field, "value": value, "requirement": "LINK-010"},
        )
