"""Exact-integer supported subset of TS 38.214 transport-block determination."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from nr_ran_sim.errors import ModelDomainError
from nr_ran_sim.radio.nr_tables import SMALL_TBS_TABLE, McsTableEntry

TBS_PROFILE_ID = "ts38214-r18-v18.9.0-one-codeword-v1"


@dataclass(frozen=True, slots=True)
class TransportBlockResult:
    profile_id: str
    branch: Literal["zero-resource", "small-table", "large-low-rate", "large", "large-segmented"]
    allocated_prbs: int
    data_re_per_prb: int
    total_data_re: int
    modulation_order: int
    target_code_rate_x1024: int
    layers: int
    scaling_numerator: int
    scaling_denominator: int
    n_info_numerator: int
    n_info_denominator: int
    quantized_n_info_bits: int
    code_block_count: int
    transport_block_bits: int

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "branch": self.branch,
            "allocated_prbs": self.allocated_prbs,
            "data_re_per_prb": self.data_re_per_prb,
            "total_data_re": self.total_data_re,
            "modulation_order": self.modulation_order,
            "target_code_rate_x1024": self.target_code_rate_x1024,
            "layers": self.layers,
            "scaling_numerator": self.scaling_numerator,
            "scaling_denominator": self.scaling_denominator,
            "n_info_numerator": self.n_info_numerator,
            "n_info_denominator": self.n_info_denominator,
            "quantized_n_info_bits": self.quantized_n_info_bits,
            "code_block_count": self.code_block_count,
            "transport_block_bits": self.transport_block_bits,
        }


def determine_transport_block_size(
    *,
    allocated_prbs: int,
    data_re_per_prb: int,
    mcs: McsTableEntry,
    layers: int = 1,
    scaling_numerator: int = 1,
    scaling_denominator: int = 1,
) -> TransportBlockResult:
    """Calculate one-codeword TBS while retaining every integer decision term."""

    _nonnegative("allocated_prbs", allocated_prbs)
    _bounded("data_re_per_prb", data_re_per_prb, 0, 156)
    _bounded("layers", layers, 1, 1)
    _bounded("scaling_denominator", scaling_denominator, 1, 10**9)
    _bounded("scaling_numerator", scaling_numerator, 1, scaling_denominator)
    total_re = allocated_prbs * data_re_per_prb
    n_info = Fraction(
        total_re * mcs.modulation_order * mcs.code_rate_x1024 * layers * scaling_numerator,
        1024 * scaling_denominator,
    )
    if total_re == 0:
        return _build_result(
            "zero-resource",
            allocated_prbs,
            data_re_per_prb,
            total_re,
            mcs,
            layers,
            scaling_numerator,
            scaling_denominator,
            n_info,
            0,
            0,
            0,
        )
    if n_info <= 3824:
        exponent = max(3, _floor_log2(n_info) - 6)
        quantum = 1 << exponent
        quantized = max(24, quantum * (n_info.numerator // (n_info.denominator * quantum)))
        tbs = next(value for value in SMALL_TBS_TABLE if value >= quantized)
        return _build_result(
            "small-table",
            allocated_prbs,
            data_re_per_prb,
            total_re,
            mcs,
            layers,
            scaling_numerator,
            scaling_denominator,
            n_info,
            quantized,
            1,
            tbs,
        )
    shifted = n_info - 24
    exponent = _floor_log2(shifted) - 5
    quantum = 1 << exponent
    rounded = _round_half_up(shifted / quantum)
    quantized = max(3840, quantum * rounded)
    if mcs.code_rate_x1024 <= 256:
        blocks = _ceil_div(quantized + 24, 3816)
        tbs = 8 * blocks * _ceil_div(quantized + 24, 8 * blocks) - 24
        branch: Literal["large-low-rate", "large", "large-segmented"] = "large-low-rate"
    elif quantized > 8424:
        blocks = _ceil_div(quantized + 24, 8424)
        tbs = 8 * blocks * _ceil_div(quantized + 24, 8 * blocks) - 24
        branch = "large-segmented"
    else:
        blocks = 1
        tbs = 8 * _ceil_div(quantized + 24, 8) - 24
        branch = "large"
    return _build_result(
        branch,
        allocated_prbs,
        data_re_per_prb,
        total_re,
        mcs,
        layers,
        scaling_numerator,
        scaling_denominator,
        n_info,
        quantized,
        blocks,
        tbs,
    )


def _build_result(
    branch: Literal["zero-resource", "small-table", "large-low-rate", "large", "large-segmented"],
    allocated_prbs: int,
    data_re_per_prb: int,
    total_re: int,
    mcs: McsTableEntry,
    layers: int,
    scaling_numerator: int,
    scaling_denominator: int,
    n_info: Fraction,
    quantized: int,
    blocks: int,
    tbs: int,
) -> TransportBlockResult:
    return TransportBlockResult(
        profile_id=TBS_PROFILE_ID,
        branch=branch,
        allocated_prbs=allocated_prbs,
        data_re_per_prb=data_re_per_prb,
        total_data_re=total_re,
        modulation_order=mcs.modulation_order,
        target_code_rate_x1024=mcs.code_rate_x1024,
        layers=layers,
        scaling_numerator=scaling_numerator,
        scaling_denominator=scaling_denominator,
        n_info_numerator=n_info.numerator,
        n_info_denominator=n_info.denominator,
        quantized_n_info_bits=quantized,
        code_block_count=blocks,
        transport_block_bits=tbs,
    )


def _floor_log2(value: Fraction) -> int:
    if value <= 0:
        raise ModelDomainError(
            "log2 input must be positive",
            {"value": str(value), "requirement": "LINK-013"},
        )
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if exponent >= 0:
        if value.numerator < value.denominator * (1 << exponent):
            exponent -= 1
    elif value.numerator * (1 << -exponent) < value.denominator:
        exponent -= 1
    return exponent


def _round_half_up(value: Fraction) -> int:
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def _nonnegative(field: str, value: int) -> None:
    if value < 0:
        raise ModelDomainError(
            f"{field} must be nonnegative",
            {"field": field, "value": value, "requirement": "LINK-013"},
        )


def _bounded(field: str, value: int, lower: int, upper: int) -> None:
    if not lower <= value <= upper:
        raise ModelDomainError(
            f"{field} is outside the supported Tier A domain",
            {
                "field": field,
                "value": value,
                "minimum": lower,
                "maximum": upper,
                "requirement": "LINK-013",
            },
        )
