"""Deterministic Tier A Round Robin, Max-C/I, and Proportional Fair policies."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from nr_ran_sim.config.normalize import NormalizedScheduler
from nr_ran_sim.errors import InvariantViolation
from nr_ran_sim.mac.models import (
    AllocationDecision,
    PrbAllocation,
    SchedulerObservation,
    ServiceFeedback,
    decimal_state_value,
    validate_decision,
)


class SchedulerPolicy(Protocol):
    policy_id: str

    def decide(self, observation: SchedulerObservation) -> AllocationDecision: ...

    def record_service(self, feedback: ServiceFeedback) -> None: ...

    def state(self) -> tuple[tuple[str, str], ...]: ...


class RoundRobinScheduler:
    """Split PRBs equally; rotate which lexical UE receives the first remainder PRB."""

    policy_id = "round-robin-v1"

    def __init__(self) -> None:
        self._cursor_by_cell: dict[str, int] = {}

    def decide(self, observation: SchedulerObservation) -> AllocationDecision:
        candidates = observation.candidates
        if not candidates:
            decision = _decision(
                self.policy_id, observation, (), {"eligible_count": "0"}, self.state()
            )
            validate_decision(observation, decision)
            return decision
        cursor = self._cursor_by_cell.get(observation.cell_id, 0) % len(candidates)
        ordered = candidates[cursor:] + candidates[:cursor]
        quotient, remainder = divmod(observation.available_prbs, len(candidates))
        amounts = {
            candidate.ue_id: quotient + (1 if ordinal < remainder else 0)
            for ordinal, candidate in enumerate(ordered)
        }
        allocations = tuple(
            PrbAllocation(ue_id=ue_id, prbs=amounts[ue_id])
            for ue_id in sorted(amounts)
            if amounts[ue_id] > 0
        )
        self._cursor_by_cell[observation.cell_id] = (cursor + 1) % len(candidates)
        decision = _decision(
            self.policy_id,
            observation,
            allocations,
            {
                "cursor_before": str(cursor),
                "eligible_count": str(len(candidates)),
                "remainder_prbs": str(remainder),
                "rotated_order": ",".join(candidate.ue_id for candidate in ordered),
            },
            self.state(),
        )
        validate_decision(observation, decision)
        return decision

    def record_service(self, feedback: ServiceFeedback) -> None:
        del feedback

    def state(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (f"cursor/{cell_id}", str(cursor))
            for cell_id, cursor in sorted(self._cursor_by_cell.items())
        )


class MaxCiScheduler:
    """Give all PRBs to the UE with the largest full-allocation payload."""

    policy_id = "max-ci-v1"

    def decide(self, observation: SchedulerObservation) -> AllocationDecision:
        if not observation.candidates:
            decision = _decision(self.policy_id, observation, (), {"eligible_count": "0"}, ())
            validate_decision(observation, decision)
            return decision
        winner = sorted(
            observation.candidates,
            key=lambda candidate: (-candidate.achievable_payload_bits, candidate.ue_id),
        )[0]
        decision = _decision(
            self.policy_id,
            observation,
            (PrbAllocation(winner.ue_id, observation.available_prbs),),
            {
                "eligible_count": str(len(observation.candidates)),
                "ranking_metric": "full-allocation-transport-payload-bits",
                "winning_metric": str(winner.achievable_payload_bits),
                "winning_ue_id": winner.ue_id,
            },
            (),
        )
        validate_decision(observation, decision)
        return decision

    def record_service(self, feedback: ServiceFeedback) -> None:
        del feedback

    def state(self) -> tuple[tuple[str, str], ...]:
        return ()


class ProportionalFairScheduler:
    """Rank full-allocation rate over exponentially averaged served rate."""

    policy_id = "proportional-fair-v1"

    def __init__(self, averaging_alpha: Decimal, initial_rate_floor_bps: Decimal) -> None:
        if not Decimal(0) < averaging_alpha <= Decimal(1) or initial_rate_floor_bps <= 0:
            raise InvariantViolation(
                "proportional-fair parameters are outside the configured domain",
                {"requirement": "MAC-006"},
            )
        self.averaging_alpha = averaging_alpha
        self.initial_rate_floor_bps = initial_rate_floor_bps
        self._average_rate_bps: dict[tuple[str, str], Decimal] = {}

    def decide(self, observation: SchedulerObservation) -> AllocationDecision:
        if not observation.candidates:
            decision = _decision(
                self.policy_id, observation, (), {"eligible_count": "0"}, self.state()
            )
            validate_decision(observation, decision)
            return decision
        metrics: dict[str, Decimal] = {}
        for candidate in observation.candidates:
            key = (observation.cell_id, candidate.ue_id)
            average = self._average_rate_bps.setdefault(key, self.initial_rate_floor_bps)
            metrics[candidate.ue_id] = Decimal(candidate.achievable_rate_bps) / average
        winner_id = sorted(metrics, key=lambda ue_id: (-metrics[ue_id], ue_id))[0]
        diagnostics = {
            "averaging_alpha": decimal_state_value(self.averaging_alpha),
            "eligible_count": str(len(observation.candidates)),
            "initial_rate_floor_bps": decimal_state_value(self.initial_rate_floor_bps),
            "ranking_metric": "full-allocation-rate/ewma-served-rate",
            "winning_metric": decimal_state_value(metrics[winner_id]),
            "winning_ue_id": winner_id,
        }
        diagnostics.update(
            {
                f"metric/{ue_id}": decimal_state_value(metric)
                for ue_id, metric in sorted(metrics.items())
            }
        )
        decision = _decision(
            self.policy_id,
            observation,
            (PrbAllocation(winner_id, observation.available_prbs),),
            diagnostics,
            self.state(),
        )
        validate_decision(observation, decision)
        return decision

    def record_service(self, feedback: ServiceFeedback) -> None:
        served = dict(feedback.served_bits)
        alpha = self.averaging_alpha
        for ue_id in feedback.eligible_ue_ids:
            key = (feedback.cell_id, ue_id)
            previous = self._average_rate_bps.setdefault(key, self.initial_rate_floor_bps)
            realized_rate = (
                Decimal(served.get(ue_id, 0)) * Decimal(1_000_000_000) / feedback.interval_ns
            )
            self._average_rate_bps[key] = (Decimal(1) - alpha) * previous + alpha * realized_rate

    def state(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (
                f"average_rate_bps/{cell_id}/{ue_id}",
                decimal_state_value(average),
            )
            for (cell_id, ue_id), average in sorted(self._average_rate_bps.items())
        )


def build_scheduler(configuration: NormalizedScheduler) -> SchedulerPolicy:
    if configuration.policy == "round-robin":
        return RoundRobinScheduler()
    if configuration.policy == "max-ci":
        return MaxCiScheduler()
    if configuration.policy == "proportional-fair":
        if configuration.averaging_alpha is None or configuration.initial_rate_floor_bps is None:
            raise InvariantViolation(
                "normalized PF configuration is missing required parameters",
                {"requirement": "MAC-006"},
            )
        return ProportionalFairScheduler(
            configuration.averaging_alpha,
            configuration.initial_rate_floor_bps,
        )
    raise InvariantViolation(
        "normalized scheduler policy is unsupported",
        {"policy": configuration.policy, "requirement": "MAC-001"},
    )


def _decision(
    policy_id: str,
    observation: SchedulerObservation,
    allocations: tuple[PrbAllocation, ...],
    diagnostics: dict[str, str],
    state: tuple[tuple[str, str], ...],
) -> AllocationDecision:
    return AllocationDecision(
        policy_id=policy_id,
        tick=observation.tick,
        cell_id=observation.cell_id,
        allocations=tuple(sorted(allocations, key=lambda item: item.ue_id)),
        diagnostics=tuple(sorted(diagnostics.items())),
        state=state,
    )
