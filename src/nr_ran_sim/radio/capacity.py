"""Compose NR resources, analytical link adaptation, and transport capacity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nr_ran_sim.config.normalize import NormalizedRadio
from nr_ran_sim.errors import ModelDomainError
from nr_ran_sim.radio.link_adaptation import LinkAdaptationResult, select_link_adaptation
from nr_ran_sim.radio.resources import ResourceGrid, build_resource_grid
from nr_ran_sim.radio.tbs import TransportBlockResult, determine_transport_block_size

CAPACITY_PROFILE_ID = "single-layer-static-tbs-capacity-v1"


@dataclass(frozen=True, slots=True)
class CapacityResult:
    profile_id: str
    interpretation: str
    state: Literal[
        "zero_resource",
        "outage_below_cqi1",
        "cqi_without_supported_mcs",
        "capacity_available",
    ]
    allocated_prbs: int
    resource_grid: ResourceGrid
    adaptation: LinkAdaptationResult
    transport_block: TransportBlockResult | None
    capacity_bits_per_interval: int
    capacity_bit_rate_bps: int

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "interpretation": self.interpretation,
            "state": self.state,
            "allocated_prbs": self.allocated_prbs,
            "resource_grid": self.resource_grid.as_dict(),
            "adaptation": self.adaptation.as_dict(),
            "transport_block": (
                None if self.transport_block is None else self.transport_block.as_dict()
            ),
            "capacity_bits_per_interval": self.capacity_bits_per_interval,
            "capacity_bit_rate_bps": self.capacity_bit_rate_bps,
        }


def evaluate_capacity(
    radio: NormalizedRadio,
    *,
    sinr_db: float,
    allocated_prbs: int,
) -> CapacityResult:
    """Evaluate service capacity for an allocation without making a scheduling decision."""

    grid = build_resource_grid(radio)
    if not 0 <= allocated_prbs <= grid.prb_count:
        raise ModelDomainError(
            "allocated PRBs must be within the cell resource-grid capacity",
            {
                "allocated_prbs": allocated_prbs,
                "available_prbs": grid.prb_count,
                "requirement": "LINK-009",
            },
        )
    adaptation = select_link_adaptation(sinr_db, float(radio.implementation_margin_db))
    if allocated_prbs == 0 or grid.tbs_data_re_per_prb == 0:
        return _capacity_result("zero_resource", allocated_prbs, grid, adaptation, None)
    if adaptation.mcs is None:
        state: Literal["outage_below_cqi1", "cqi_without_supported_mcs"] = (
            "outage_below_cqi1"
            if adaptation.state == "outage_below_cqi1"
            else "cqi_without_supported_mcs"
        )
        return _capacity_result(state, allocated_prbs, grid, adaptation, None)
    transport_block = determine_transport_block_size(
        allocated_prbs=allocated_prbs,
        data_re_per_prb=grid.tbs_data_re_per_prb,
        mcs=adaptation.mcs,
        layers=radio.layers,
    )
    return _capacity_result(
        "capacity_available",
        allocated_prbs,
        grid,
        adaptation,
        transport_block,
    )


def _capacity_result(
    state: Literal[
        "zero_resource",
        "outage_below_cqi1",
        "cqi_without_supported_mcs",
        "capacity_available",
    ],
    allocated_prbs: int,
    grid: ResourceGrid,
    adaptation: LinkAdaptationResult,
    transport_block: TransportBlockResult | None,
) -> CapacityResult:
    bits = 0 if transport_block is None else transport_block.transport_block_bits
    rate = bits * 1_000_000_000 // grid.scheduling_interval_ns
    return CapacityResult(
        profile_id=CAPACITY_PROFILE_ID,
        interpretation="allocation-conditional-transport-capacity-not-observed-throughput",
        state=state,
        allocated_prbs=allocated_prbs,
        resource_grid=grid,
        adaptation=adaptation,
        transport_block=transport_block,
        capacity_bits_per_interval=bits,
        capacity_bit_rate_bps=rate,
    )
