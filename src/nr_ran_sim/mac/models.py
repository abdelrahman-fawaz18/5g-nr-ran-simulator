"""Immutable scheduler observations, decisions, feedback, and allocation invariants."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from nr_ran_sim.errors import InvariantViolation


@dataclass(frozen=True, slots=True)
class SchedulingCandidate:
    ue_id: str
    queue_payload_bits: int
    achievable_payload_bits: int
    achievable_rate_bps: int
    sinr_db: float

    def __post_init__(self) -> None:
        if (
            not self.ue_id
            or self.queue_payload_bits <= 0
            or self.achievable_payload_bits < 0
            or self.achievable_rate_bps < 0
            or not math.isfinite(self.sinr_db)
        ):
            raise InvariantViolation(
                "scheduler candidate is outside the Tier A domain",
                {"ue_id": self.ue_id, "requirement": "MAC-002"},
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "ue_id": self.ue_id,
            "queue_payload_bits": self.queue_payload_bits,
            "achievable_payload_bits": self.achievable_payload_bits,
            "achievable_rate_bps": self.achievable_rate_bps,
            "sinr_db": self.sinr_db,
        }


@dataclass(frozen=True, slots=True)
class SchedulerObservation:
    tick: int
    interval_ns: int
    cell_id: str
    available_prbs: int
    candidates: tuple[SchedulingCandidate, ...]

    def __post_init__(self) -> None:
        candidate_ids = tuple(candidate.ue_id for candidate in self.candidates)
        if (
            self.tick < 0
            or self.interval_ns <= 0
            or not self.cell_id
            or self.available_prbs <= 0
            or candidate_ids != tuple(sorted(candidate_ids))
            or len(set(candidate_ids)) != len(candidate_ids)
        ):
            raise InvariantViolation(
                "scheduler observation violates ordering or resource invariants",
                {
                    "tick": self.tick,
                    "cell_id": self.cell_id,
                    "available_prbs": self.available_prbs,
                    "candidate_ids": candidate_ids,
                    "requirement": "MAC-001",
                },
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "tick": self.tick,
            "interval_ns": self.interval_ns,
            "cell_id": self.cell_id,
            "available_prbs": self.available_prbs,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class PrbAllocation:
    ue_id: str
    prbs: int

    def as_dict(self) -> dict[str, object]:
        return {"ue_id": self.ue_id, "prbs": self.prbs}


@dataclass(frozen=True, slots=True)
class AllocationDecision:
    policy_id: str
    tick: int
    cell_id: str
    allocations: tuple[PrbAllocation, ...]
    diagnostics: tuple[tuple[str, str], ...]
    state: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "tick": self.tick,
            "cell_id": self.cell_id,
            "allocations": [allocation.as_dict() for allocation in self.allocations],
            "diagnostics": dict(self.diagnostics),
            "state": dict(self.state),
        }


@dataclass(frozen=True, slots=True)
class ServiceFeedback:
    cell_id: str
    completion_tick: int
    interval_ns: int
    eligible_ue_ids: tuple[str, ...]
    served_bits: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        served_ids = tuple(ue_id for ue_id, _ in self.served_bits)
        if (
            not self.cell_id
            or self.completion_tick <= 0
            or self.interval_ns <= 0
            or self.eligible_ue_ids != tuple(sorted(self.eligible_ue_ids))
            or len(set(self.eligible_ue_ids)) != len(self.eligible_ue_ids)
            or served_ids != tuple(sorted(served_ids))
            or any(type(bits) is not int or bits < 0 for _, bits in self.served_bits)
            or not set(served_ids).issubset(self.eligible_ue_ids)
        ):
            raise InvariantViolation(
                "scheduler service feedback violates the policy-state contract",
                {"cell_id": self.cell_id, "requirement": "MAC-007"},
            )


def validate_decision(
    observation: SchedulerObservation,
    decision: AllocationDecision,
) -> None:
    """Reject policy output that violates the common resource contract."""

    if decision.tick != observation.tick or decision.cell_id != observation.cell_id:
        raise InvariantViolation(
            "scheduler decision does not match its observation",
            {
                "observation_tick": observation.tick,
                "decision_tick": decision.tick,
                "requirement": "MAC-001",
            },
        )
    eligible = {candidate.ue_id for candidate in observation.candidates}
    allocation_ids = tuple(allocation.ue_id for allocation in decision.allocations)
    if allocation_ids != tuple(sorted(allocation_ids)) or len(set(allocation_ids)) != len(
        allocation_ids
    ):
        raise InvariantViolation(
            "scheduler allocations must be unique and sorted by UE identifier",
            {"allocation_ids": allocation_ids, "requirement": "MAC-003"},
        )
    total = 0
    for allocation in decision.allocations:
        if allocation.ue_id not in eligible:
            raise InvariantViolation(
                "scheduler allocated resources to an ineligible UE",
                {"ue_id": allocation.ue_id, "requirement": "MAC-002"},
            )
        if type(allocation.prbs) is not int or allocation.prbs <= 0:
            raise InvariantViolation(
                "scheduler allocations must use positive integer PRBs",
                {
                    "ue_id": allocation.ue_id,
                    "prbs": allocation.prbs,
                    "requirement": "MAC-002",
                },
            )
        total += allocation.prbs
    if total > observation.available_prbs:
        raise InvariantViolation(
            "scheduler allocation exceeds cell PRB capacity",
            {
                "allocated_prbs": total,
                "available_prbs": observation.available_prbs,
                "requirement": "MAC-002",
            },
        )


def decimal_state_value(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")
