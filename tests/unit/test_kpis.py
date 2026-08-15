from __future__ import annotations

from typing import Any

import pytest

from nr_ran_sim.config.models import ScenarioConfig
from nr_ran_sim.config.normalize import normalize_scenario
from nr_ran_sim.domain import PacketCohort, PacketId, PacketRecord, PacketSnapshot, TerminalCause
from nr_ran_sim.domain.entities import build_entity_registry
from nr_ran_sim.mac import AllocationDecision, PrbAllocation
from nr_ran_sim.metrics import (
    AllocationOutcome,
    BearerServiceRecord,
    SchedulingIntervalRecord,
    build_kpi_report,
)


def _metric(report, name: str, level: str, aggregate_id: str):  # type: ignore[no-untyped-def]
    return next(
        record
        for record in report.records
        if record.name == name
        and record.aggregation_level == level
        and record.aggregation_id == aggregate_id
    )


def _completed_packet(bearer_id, ordinal: int, arrival: int, first: int, completion: int):  # type: ignore[no-untyped-def]
    packet = PacketRecord(
        id=PacketId(f"packet/{bearer_id}/{ordinal:012d}"),
        bearer_id=bearer_id,
        arrival_tick=arrival,
        payload_bits=100,
        deadline_tick=None,
        cohort=PacketCohort.MEASUREMENT,
    )
    return PacketSnapshot(
        packet=packet,
        remaining_bits=0,
        first_service_tick=first,
        completion_tick=completion,
        terminal_tick=completion,
        terminal_cause=TerminalCause.COMPLETED,
    )


def test_hand_calculated_kpi_vector_uses_contract_populations_and_formulas(
    scheduler_scenario_data: dict[str, Any],
) -> None:
    scenario = normalize_scenario(ScenarioConfig.model_validate(scheduler_scenario_data))
    entities = build_entity_registry(scenario)
    first_bearer, second_bearer = (bearer.id for bearer in entities.bearers)
    first_packets = (
        _completed_packet(first_bearer, 0, 1_000_000, 1_250_000, 2_000_000),
        _completed_packet(first_bearer, 1, 1_500_000, 1_750_000, 3_000_000),
    )
    second_packets = (_completed_packet(second_bearer, 0, 1_000_000, 1_500_000, 2_000_000),)
    first_ue, second_ue = (str(ue.id) for ue in entities.ues)
    cell_id = str(entities.cells[0].id)
    decision = AllocationDecision(
        policy_id="fixture",
        tick=1_000_000,
        cell_id=cell_id,
        allocations=(PrbAllocation(first_ue, 6), PrbAllocation(second_ue, 4)),
        diagnostics=(),
        state=(),
    )
    interval = SchedulingIntervalRecord(
        start_tick=1_000_000,
        completion_tick=1_500_000,
        cell_id=cell_id,
        available_prbs=10,
        eligible_ue_ids=(first_ue, second_ue),
        outage_ue_ids=(),
        decision=decision,
        outcomes=(
            AllocationOutcome(
                ue_id=first_ue,
                allocated_prbs=6,
                capacity_state="capacity_available",
                scheduled_capacity_bits=100,
                reserved_payload_bits=100,
                served_payload_bits=100,
                unused_capacity_bits=0,
                bearer_services=(BearerServiceRecord(str(first_bearer), 100, 100),),
            ),
            AllocationOutcome(
                ue_id=second_ue,
                allocated_prbs=4,
                capacity_state="capacity_available",
                scheduled_capacity_bits=100,
                reserved_payload_bits=0,
                served_payload_bits=0,
                unused_capacity_bits=100,
                bearer_services=(),
            ),
        ),
        policy_state_after_service=(),
    )
    report = build_kpi_report(
        scenario,
        entities,
        run_id="run/fixture",
        serving_cells={first_ue: cell_id, second_ue: cell_id},
        packet_snapshots=(
            (str(first_bearer), first_packets),
            (str(second_bearer), second_packets),
        ),
        intervals=(interval,),
    )

    duration_s = 0.004
    assert _metric(report, "offered_load_bps", "system", "system").value == pytest.approx(
        300 / duration_s
    )
    assert _metric(report, "served_throughput_bps", "system", "system").value == pytest.approx(
        100 / duration_s
    )
    assert _metric(report, "cohort_goodput_bps", "system", "system").value == pytest.approx(
        300 / duration_s
    )
    assert _metric(report, "system_delay_median_ns", "bearer", str(first_bearer)).value == (
        1_250_000
    )
    assert _metric(report, "system_delay_p95_ns", "bearer", str(first_bearer)).value == (1_475_000)
    assert (
        _metric(
            report,
            "jitter_mean_absolute_successive_delay_ns",
            "bearer",
            str(first_bearer),
        ).value
        == 500_000
    )
    assert _metric(report, "delivery_ratio", "system", "system").value == 1
    assert _metric(report, "jain_fairness", "system", "system").value == pytest.approx(0.9)
    assert _metric(report, "prb_utilization", "system", "system").value == 1
    assert _metric(report, "wasted_allocation_ratio", "system", "system").value == 0.4
    deadline = _metric(report, "deadline_success_ratio", "system", "system")
    assert deadline.value is None
    assert deadline.null_reason == "zero_denominator"
