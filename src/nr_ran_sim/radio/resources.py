"""Explicit Tier A NR resource-grid and scheduling-interval accounting."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

from nr_ran_sim.config.normalize import NormalizedRadio

SUBCARRIERS_PER_PRB = 12
NORMAL_CP_SYMBOLS_PER_SLOT = 14
TBS_MAX_RE_PER_PRB = 156
SCHEDULING_INTERVAL_SLOTS = 1
RESOURCE_GRID_PROFILE_ID = "fr1-normal-cp-single-slot-v1"
FR2_RESOURCE_GRID_PROFILE_ID = "fr2-1-normal-cp-single-slot-v1"


@dataclass(frozen=True, slots=True)
class ResourceGrid:
    profile_id: str
    frequency_range: str
    channel_bandwidth_hz: int
    subcarrier_spacing_hz: int
    numerology: int
    prb_count: int
    subcarriers_per_prb: int
    symbols_per_slot: int
    slots_per_ms: int
    slot_duration_ns: int
    scheduling_interval_slots: int
    scheduling_interval_ns: int
    gross_re_per_prb: int
    configured_overhead_fraction: str
    uncapped_data_re_per_prb: int
    tbs_max_re_per_prb: int
    tbs_data_re_per_prb: int
    tbs_cap_applied: bool
    overhead_quantization_rule: str

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "frequency_range": self.frequency_range,
            "channel_bandwidth_hz": self.channel_bandwidth_hz,
            "subcarrier_spacing_hz": self.subcarrier_spacing_hz,
            "numerology": self.numerology,
            "prb_count": self.prb_count,
            "subcarriers_per_prb": self.subcarriers_per_prb,
            "symbols_per_slot": self.symbols_per_slot,
            "slots_per_ms": self.slots_per_ms,
            "slot_duration_ns": self.slot_duration_ns,
            "scheduling_interval_slots": self.scheduling_interval_slots,
            "scheduling_interval_ns": self.scheduling_interval_ns,
            "gross_re_per_prb": self.gross_re_per_prb,
            "configured_overhead_fraction": self.configured_overhead_fraction,
            "uncapped_data_re_per_prb": self.uncapped_data_re_per_prb,
            "tbs_max_re_per_prb": self.tbs_max_re_per_prb,
            "tbs_data_re_per_prb": self.tbs_data_re_per_prb,
            "tbs_cap_applied": self.tbs_cap_applied,
            "overhead_quantization_rule": self.overhead_quantization_rule,
        }


def build_resource_grid(radio: NormalizedRadio) -> ResourceGrid:
    """Resolve the normalized radio into one explicit normal-CP slot resource grid."""

    gross = SUBCARRIERS_PER_PRB * NORMAL_CP_SYMBOLS_PER_SLOT
    data_re_decimal = Decimal(gross) * (Decimal(1) - radio.data_re_overhead_fraction)
    uncapped_data_re = int(data_re_decimal.to_integral_value(rounding=ROUND_FLOOR))
    tbs_data_re = min(TBS_MAX_RE_PER_PRB, uncapped_data_re)
    return ResourceGrid(
        profile_id=(
            RESOURCE_GRID_PROFILE_ID
            if radio.frequency_range == "FR1"
            else FR2_RESOURCE_GRID_PROFILE_ID
        ),
        frequency_range=radio.frequency_range,
        channel_bandwidth_hz=radio.channel_bandwidth_hz,
        subcarrier_spacing_hz=radio.subcarrier_spacing_hz,
        numerology=radio.numerology,
        prb_count=radio.prb_count,
        subcarriers_per_prb=SUBCARRIERS_PER_PRB,
        symbols_per_slot=NORMAL_CP_SYMBOLS_PER_SLOT,
        slots_per_ms=radio.slots_per_ms,
        slot_duration_ns=radio.slot_duration_ns,
        scheduling_interval_slots=SCHEDULING_INTERVAL_SLOTS,
        scheduling_interval_ns=radio.slot_duration_ns * SCHEDULING_INTERVAL_SLOTS,
        gross_re_per_prb=gross,
        configured_overhead_fraction=str(radio.data_re_overhead_fraction),
        uncapped_data_re_per_prb=uncapped_data_re,
        tbs_max_re_per_prb=TBS_MAX_RE_PER_PRB,
        tbs_data_re_per_prb=tbs_data_re,
        tbs_cap_applied=uncapped_data_re > TBS_MAX_RE_PER_PRB,
        overhead_quantization_rule="floor(gross_re_per_prb*(1-overhead)); then min(156, value)",
    )
