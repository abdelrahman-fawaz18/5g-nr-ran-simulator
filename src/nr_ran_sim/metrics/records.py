"""Versioned scheduler-service and KPI result records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nr_ran_sim.mac.models import AllocationDecision

NullReason = Literal[
    "insufficient_samples",
    "zero_denominator",
    "not_applicable",
    "run_failed",
]


@dataclass(frozen=True, slots=True)
class BearerServiceRecord:
    bearer_id: str
    reserved_bits: int
    served_bits: int

    def as_dict(self) -> dict[str, object]:
        return {
            "bearer_id": self.bearer_id,
            "reserved_bits": self.reserved_bits,
            "served_bits": self.served_bits,
        }


@dataclass(frozen=True, slots=True)
class AllocationOutcome:
    ue_id: str
    allocated_prbs: int
    capacity_state: str
    scheduled_capacity_bits: int
    reserved_payload_bits: int
    served_payload_bits: int
    unused_capacity_bits: int
    bearer_services: tuple[BearerServiceRecord, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ue_id": self.ue_id,
            "allocated_prbs": self.allocated_prbs,
            "capacity_state": self.capacity_state,
            "scheduled_capacity_bits": self.scheduled_capacity_bits,
            "reserved_payload_bits": self.reserved_payload_bits,
            "served_payload_bits": self.served_payload_bits,
            "unused_capacity_bits": self.unused_capacity_bits,
            "bearer_services": [item.as_dict() for item in self.bearer_services],
        }


@dataclass(frozen=True, slots=True)
class SchedulingIntervalRecord:
    start_tick: int
    completion_tick: int
    cell_id: str
    available_prbs: int
    eligible_ue_ids: tuple[str, ...]
    outage_ue_ids: tuple[str, ...]
    decision: AllocationDecision
    outcomes: tuple[AllocationOutcome, ...]
    policy_state_after_service: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "start_tick": self.start_tick,
            "completion_tick": self.completion_tick,
            "cell_id": self.cell_id,
            "available_prbs": self.available_prbs,
            "eligible_ue_ids": list(self.eligible_ue_ids),
            "outage_ue_ids": list(self.outage_ue_ids),
            "decision": self.decision.as_dict(),
            "outcomes": [outcome.as_dict() for outcome in self.outcomes],
            "policy_state_after_service": dict(self.policy_state_after_service),
        }


@dataclass(frozen=True, slots=True)
class MetricRecord:
    name: str
    definition_version: str
    unit: str
    aggregation_level: str
    aggregation_id: str
    population_filter: str
    interval_start_tick: int
    interval_end_tick: int
    sample_count: int
    run_id: str
    value: int | float | None
    null_reason: NullReason | None = None
    details: tuple[tuple[str, str | int], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "definition_version": self.definition_version,
            "unit": self.unit,
            "aggregation_level": self.aggregation_level,
            "aggregation_id": self.aggregation_id,
            "population_filter": self.population_filter,
            "interval_start_tick": self.interval_start_tick,
            "interval_end_tick": self.interval_end_tick,
            "sample_count": self.sample_count,
            "run_id": self.run_id,
            "value": self.value,
            "null_reason": self.null_reason,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class KpiReport:
    definition_version: str
    records: tuple[MetricRecord, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "definition_version": self.definition_version,
            "records": [record.as_dict() for record in self.records],
        }
