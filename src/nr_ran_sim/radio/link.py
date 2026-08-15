"""Reconstructable Tier A downlink power, noise, interference, and SINR arithmetic."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from nr_ran_sim.errors import ModelDomainError
from nr_ran_sim.radio.propagation import PathLossResult
from nr_ran_sim.radio.topology import RadioCell, RadioUe

THERMAL_NOISE_DENSITY_DBM_PER_HZ = -174.0
NOISE_MODEL_ID = "thermal-noise-minus174-v1"


@dataclass(frozen=True, slots=True)
class LinkBudgetResult:
    cell_id: str
    ue_id: str
    transmission_bandwidth_hz: int
    subcarrier_spacing_hz: int
    transmit_power_w: float
    transmit_power_dbm: float
    transmit_psd_w_per_hz: float
    transmit_psd_dbm_per_hz: float
    transmitter_gain_dbi: float
    receiver_gain_dbi: float
    basic_path_loss_db: float
    shadow_fading_db: float
    penetration_loss_db: float
    miscellaneous_loss_db: float
    total_link_loss_db: float
    received_power_w: float
    received_power_dbm: float
    received_psd_w_per_hz: float
    received_psd_dbm_per_hz: float
    reference_signal_received_power_w: float
    reference_signal_received_power_dbm: float

    def as_dict(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "ue_id": self.ue_id,
            "transmission_bandwidth_hz": self.transmission_bandwidth_hz,
            "subcarrier_spacing_hz": self.subcarrier_spacing_hz,
            "transmit_power_w": self.transmit_power_w,
            "transmit_power_dbm": self.transmit_power_dbm,
            "transmit_psd_w_per_hz": self.transmit_psd_w_per_hz,
            "transmit_psd_dbm_per_hz": self.transmit_psd_dbm_per_hz,
            "transmitter_gain_dbi": self.transmitter_gain_dbi,
            "receiver_gain_dbi": self.receiver_gain_dbi,
            "basic_path_loss_db": self.basic_path_loss_db,
            "shadow_fading_db": self.shadow_fading_db,
            "penetration_loss_db": self.penetration_loss_db,
            "miscellaneous_loss_db": self.miscellaneous_loss_db,
            "total_link_loss_db": self.total_link_loss_db,
            "received_power_w": self.received_power_w,
            "received_power_dbm": self.received_power_dbm,
            "received_psd_w_per_hz": self.received_psd_w_per_hz,
            "received_psd_dbm_per_hz": self.received_psd_dbm_per_hz,
            "reference_signal_received_power_w": self.reference_signal_received_power_w,
            "reference_signal_received_power_dbm": self.reference_signal_received_power_dbm,
        }


@dataclass(frozen=True, slots=True)
class NoiseResult:
    model_id: str
    density_dbm_per_hz: float
    bandwidth_hz: int
    receiver_noise_figure_db: float
    noise_power_w: float
    noise_power_dbm: float

    def as_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "density_dbm_per_hz": self.density_dbm_per_hz,
            "bandwidth_hz": self.bandwidth_hz,
            "receiver_noise_figure_db": self.receiver_noise_figure_db,
            "noise_power_w": self.noise_power_w,
            "noise_power_dbm": self.noise_power_dbm,
        }


@dataclass(frozen=True, slots=True)
class InterferenceComponent:
    cell_id: str
    power_w: float
    power_dbm: float

    def as_dict(self) -> dict[str, object]:
        return {"cell_id": self.cell_id, "power_w": self.power_w, "power_dbm": self.power_dbm}


@dataclass(frozen=True, slots=True)
class InterferenceResult:
    profile_id: str
    components: tuple[InterferenceComponent, ...]
    total_power_w: float
    total_power_dbm: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "components": [component.as_dict() for component in self.components],
            "total_power_w": self.total_power_w,
            "total_power_dbm": self.total_power_dbm,
        }


@dataclass(frozen=True, slots=True)
class SinrResult:
    signal_power_w: float
    signal_power_dbm: float
    interference_power_w: float
    interference_power_dbm: float | None
    noise_power_w: float
    noise_power_dbm: float
    denominator_power_w: float
    denominator_power_dbm: float
    sinr_linear: float
    sinr_db: float

    def as_dict(self) -> dict[str, object]:
        return {
            "signal_power_w": self.signal_power_w,
            "signal_power_dbm": self.signal_power_dbm,
            "interference_power_w": self.interference_power_w,
            "interference_power_dbm": self.interference_power_dbm,
            "noise_power_w": self.noise_power_w,
            "noise_power_dbm": self.noise_power_dbm,
            "denominator_power_w": self.denominator_power_w,
            "denominator_power_dbm": self.denominator_power_dbm,
            "sinr_linear": self.sinr_linear,
            "sinr_db": self.sinr_db,
        }


def calculate_link_budget(
    cell: RadioCell,
    ue: RadioUe,
    path_loss: PathLossResult,
    *,
    transmission_bandwidth_hz: int,
    subcarrier_spacing_hz: int,
) -> LinkBudgetResult:
    _positive_integer("transmission_bandwidth_hz", transmission_bandwidth_hz)
    _positive_integer("subcarrier_spacing_hz", subcarrier_spacing_hz)
    total_loss = (
        path_loss.basic_path_loss_db
        + path_loss.shadow_fading_db
        + ue.penetration_loss_db
        + cell.miscellaneous_loss_db
    )
    received_dbm = (
        cell.transmit_power_dbm + cell.antenna_gain_dbi + ue.antenna_gain_dbi - total_loss
    )
    transmit_psd_w = cell.transmit_power_w / transmission_bandwidth_hz
    received_w = dbm_to_watt(received_dbm)
    received_psd_w = received_w / transmission_bandwidth_hz
    reference_w = received_psd_w * subcarrier_spacing_hz
    return LinkBudgetResult(
        cell_id=cell.id,
        ue_id=ue.id,
        transmission_bandwidth_hz=transmission_bandwidth_hz,
        subcarrier_spacing_hz=subcarrier_spacing_hz,
        transmit_power_w=cell.transmit_power_w,
        transmit_power_dbm=cell.transmit_power_dbm,
        transmit_psd_w_per_hz=transmit_psd_w,
        transmit_psd_dbm_per_hz=watt_to_dbm(transmit_psd_w),
        transmitter_gain_dbi=cell.antenna_gain_dbi,
        receiver_gain_dbi=ue.antenna_gain_dbi,
        basic_path_loss_db=path_loss.basic_path_loss_db,
        shadow_fading_db=path_loss.shadow_fading_db,
        penetration_loss_db=ue.penetration_loss_db,
        miscellaneous_loss_db=cell.miscellaneous_loss_db,
        total_link_loss_db=total_loss,
        received_power_w=received_w,
        received_power_dbm=received_dbm,
        received_psd_w_per_hz=received_psd_w,
        received_psd_dbm_per_hz=watt_to_dbm(received_psd_w),
        reference_signal_received_power_w=reference_w,
        reference_signal_received_power_dbm=watt_to_dbm(reference_w),
    )


def thermal_noise(
    bandwidth_hz: int,
    receiver_noise_figure_db: float,
) -> NoiseResult:
    _positive_integer("bandwidth_hz", bandwidth_hz)
    if not math.isfinite(receiver_noise_figure_db) or receiver_noise_figure_db < 0.0:
        raise ModelDomainError(
            "receiver noise figure must be finite and nonnegative",
            {
                "receiver_noise_figure_db": receiver_noise_figure_db,
                "requirement": "LINK-002",
            },
        )
    power_dbm = (
        THERMAL_NOISE_DENSITY_DBM_PER_HZ
        + 10.0 * math.log10(bandwidth_hz)
        + receiver_noise_figure_db
    )
    return NoiseResult(
        model_id=NOISE_MODEL_ID,
        density_dbm_per_hz=THERMAL_NOISE_DENSITY_DBM_PER_HZ,
        bandwidth_hz=bandwidth_hz,
        receiver_noise_figure_db=receiver_noise_figure_db,
        noise_power_w=dbm_to_watt(power_dbm),
        noise_power_dbm=power_dbm,
    )


def aggregate_interference(
    profile_id: Literal["noise_limited-v1", "full_buffer_reuse1-v1"],
    serving_cell_id: str,
    links: tuple[LinkBudgetResult, ...],
) -> InterferenceResult:
    if profile_id == "noise_limited-v1":
        return InterferenceResult(
            profile_id=profile_id,
            components=(),
            total_power_w=0.0,
            total_power_dbm=None,
        )
    components = tuple(
        InterferenceComponent(
            cell_id=link.cell_id,
            power_w=link.received_power_w,
            power_dbm=link.received_power_dbm,
        )
        for link in sorted(links, key=lambda item: item.cell_id)
        if link.cell_id != serving_cell_id
    )
    total_w = math.fsum(component.power_w for component in components)
    return InterferenceResult(
        profile_id=profile_id,
        components=components,
        total_power_w=total_w,
        total_power_dbm=None if total_w == 0.0 else watt_to_dbm(total_w),
    )


def calculate_sinr(
    signal: LinkBudgetResult,
    noise: NoiseResult,
    interference: InterferenceResult,
) -> SinrResult:
    denominator = noise.noise_power_w + interference.total_power_w
    if denominator <= 0.0 or not math.isfinite(denominator):
        raise ModelDomainError(
            "SINR denominator must be finite and positive",
            {"denominator_power_w": denominator, "requirement": "LINK-004"},
        )
    ratio = signal.received_power_w / denominator
    return SinrResult(
        signal_power_w=signal.received_power_w,
        signal_power_dbm=signal.received_power_dbm,
        interference_power_w=interference.total_power_w,
        interference_power_dbm=interference.total_power_dbm,
        noise_power_w=noise.noise_power_w,
        noise_power_dbm=noise.noise_power_dbm,
        denominator_power_w=denominator,
        denominator_power_dbm=watt_to_dbm(denominator),
        sinr_linear=ratio,
        sinr_db=10.0 * math.log10(ratio),
    )


def dbm_to_watt(power_dbm: float) -> float:
    if not math.isfinite(power_dbm):
        raise ModelDomainError(
            "dBm power must be finite",
            {"power_dbm": power_dbm, "requirement": "LINK-001"},
        )
    return float(10.0 ** ((power_dbm - 30.0) / 10.0))


def watt_to_dbm(power_w: float) -> float:
    if not math.isfinite(power_w) or power_w <= 0.0:
        raise ModelDomainError(
            "linear power must be finite and positive before conversion to dBm",
            {"power_w": power_w, "requirement": "LINK-001"},
        )
    return 10.0 * math.log10(power_w) + 30.0


def _positive_integer(field: str, value: int) -> None:
    if value <= 0:
        raise ModelDomainError(
            f"{field} must be positive",
            {"field": field, "value": value, "requirement": "LINK-002"},
        )
