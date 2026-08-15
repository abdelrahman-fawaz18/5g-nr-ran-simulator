"""Integrated deterministic Tier A scheduler, queue-service, and KPI simulation."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TypeVar

from nr_ran_sim.config.manifest import ManifestEnvelope, build_manifest
from nr_ran_sim.config.normalize import NormalizedScenario
from nr_ran_sim.domain import BearerId, PacketSnapshot, build_entity_registry
from nr_ran_sim.domain.entities import EntityRegistry
from nr_ran_sim.domain.packets import PacketRecord
from nr_ran_sim.errors import ArtifactError, InvariantViolation
from nr_ran_sim.experiments.identity import (
    RunIdentity,
    RunMetadata,
    build_exogenous_configuration_sha256,
    build_run_identity,
    build_run_metadata,
)
from nr_ran_sim.experiments.seeds import RngStreamRecord, SemanticRngRegistry
from nr_ran_sim.kernel import (
    DeterministicKernel,
    EventKind,
    EventPhase,
    EventResult,
    ScheduledEvent,
    SemanticTrace,
    create_scheduled_event,
)
from nr_ran_sim.kernel.events import TraceValue
from nr_ran_sim.mac import (
    AllocationDecision,
    SchedulerObservation,
    SchedulerPolicy,
    SchedulingCandidate,
    ServiceFeedback,
    build_scheduler,
)
from nr_ran_sim.metrics import (
    AllocationOutcome,
    BearerServiceRecord,
    KpiReport,
    SchedulingIntervalRecord,
    build_kpi_report,
)
from nr_ran_sim.radio.capacity import CapacityResult, evaluate_capacity
from nr_ran_sim.radio.snapshot import RadioSnapshot, build_radio_snapshot, canonicalize_floats
from nr_ran_sim.traffic.commands import CensorQueue, EnqueuePacket, ExpirePacket
from nr_ran_sim.traffic.queue import BearerQueue, QueueLedger, ServiceReservation, ServiceResult
from nr_ran_sim.traffic.sources import TrafficSourceDiagnostic, build_traffic_generator

SIMULATION_RESULT_SCHEMA_VERSION = "1.0"
PayloadT = TypeVar("PayloadT")


@dataclass(frozen=True, slots=True)
class _SchedulingTick:
    cell_id: str
    slot_ordinal: int


@dataclass(frozen=True, slots=True)
class _UeServicePlan:
    ue_id: str
    allocated_prbs: int
    capacity: CapacityResult
    reservations: tuple[ServiceReservation, ...]


@dataclass(frozen=True, slots=True)
class _SlotServicePlan:
    observation: SchedulerObservation
    decision: AllocationDecision
    completion_tick: int
    ue_plans: tuple[_UeServicePlan, ...]


@dataclass(slots=True)
class _Runtime:
    scenario: NormalizedScenario
    entities: EntityRegistry
    queues: dict[BearerId, BearerQueue]
    bearers_by_ue: dict[str, tuple[BearerId, ...]]
    serving_cell_by_ue: dict[str, str]
    sinr_by_ue: dict[str, float]
    full_capacity_by_ue: dict[str, CapacityResult]
    scheduler: SchedulerPolicy
    intervals: list[SchedulingIntervalRecord]


@dataclass(frozen=True, slots=True)
class SimulationResult:
    schema_version: str
    semantic_sha256: str
    configuration_manifest: ManifestEnvelope
    exogenous_configuration_sha256: str
    identity: RunIdentity
    radio_snapshot: RadioSnapshot
    scheduler_policy_id: str
    trace: SemanticTrace
    intervals: tuple[SchedulingIntervalRecord, ...]
    kpis: KpiReport
    queue_ledgers: tuple[tuple[str, QueueLedger], ...]
    packet_snapshots: tuple[tuple[str, tuple[PacketSnapshot, ...]], ...]
    rng_streams: tuple[RngStreamRecord, ...]
    source_diagnostics: tuple[TrafficSourceDiagnostic, ...]
    metadata: RunMetadata

    def semantic_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "configuration_manifest": self.configuration_manifest.as_dict(),
            "exogenous_configuration_sha256": self.exogenous_configuration_sha256,
            "identity": self.identity.as_dict(),
            "radio_snapshot": self.radio_snapshot.as_dict(),
            "scheduler_policy_id": self.scheduler_policy_id,
            "trace": self.trace.as_dict(),
            "intervals": [interval.as_dict() for interval in self.intervals],
            "kpis": self.kpis.as_dict(),
            "queue_ledgers": {
                bearer_id: asdict(ledger) for bearer_id, ledger in self.queue_ledgers
            },
            "packet_snapshots": {
                bearer_id: [_snapshot_dict(snapshot) for snapshot in snapshots]
                for bearer_id, snapshots in self.packet_snapshots
            },
            "rng_streams": [asdict(record) for record in self.rng_streams],
            "source_diagnostics": [asdict(item) for item in self.source_diagnostics],
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_dict(),
            "semantic_sha256": self.semantic_sha256,
            "metadata": self.metadata.as_dict(),
        }

    def to_json(self) -> str:
        return (
            json.dumps(
                canonicalize_floats(self.as_dict()),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )

    def write(self, path: Path, *, force: bool = False) -> None:
        if path.exists() and not force:
            raise ArtifactError(
                "output simulation result already exists; pass --force to replace it",
                {"path": str(path)},
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_text(self.to_json(), encoding="utf-8", newline="\n")
            temporary.replace(path)
        except OSError as exc:
            raise ArtifactError(
                "unable to commit simulation result",
                {"path": str(path), "detail": str(exc)},
            ) from exc
        finally:
            if temporary.exists():
                temporary.unlink()


def run_system_simulation(
    scenario: NormalizedScenario,
    *,
    master_seed: str,
    replication_id: int,
    code_revision: str,
    working_tree_dirty: bool,
    experiment_factors: dict[str, str] | None = None,
) -> SimulationResult:
    """Run the static-radio Tier A scheduler and queue pipeline through drain end."""

    _validate_slot_boundaries(scenario)
    manifest = build_manifest(scenario)
    exogenous_id = build_exogenous_configuration_sha256(scenario)
    identity = build_run_identity(
        configuration_sha256=manifest.configuration_sha256,
        master_seed=master_seed,
        replication_id=replication_id,
        code_revision=code_revision,
        model_profiles={
            **{str(key): str(value) for key, value in scenario.models.model_dump().items()},
            "scheduler": scenario.scheduler.policy,
            "kpi_definition": "1.0",
        },
        experiment_factors=(
            {"scheduler_policy": scenario.scheduler.policy}
            if experiment_factors is None
            else experiment_factors
        ),
    )
    radio_snapshot = build_radio_snapshot(
        scenario,
        master_seed=master_seed,
        replication_id=replication_id,
        randomness_baseline_id=exogenous_id,
    )
    entities = build_entity_registry(scenario)
    traffic_registry = SemanticRngRegistry(exogenous_id, master_seed, replication_id)
    queues, diagnostics, packets = _build_traffic_state(
        scenario,
        entities,
        traffic_registry,
    )
    serving_cell_by_ue = {
        association.ue_id: association.serving_cell_id
        for association in radio_snapshot.associations
    }
    sinr_by_ue = {
        association.ue_id: association.sinr.sinr_db for association in radio_snapshot.associations
    }
    full_capacity_by_ue = {
        ue_id: evaluate_capacity(
            scenario.radio,
            sinr_db=sinr,
            allocated_prbs=scenario.radio.prb_count,
        )
        for ue_id, sinr in sinr_by_ue.items()
    }
    bearers_by_ue: dict[str, list[BearerId]] = defaultdict(list)
    for bearer in entities.bearers:
        bearers_by_ue[str(bearer.ue_id)].append(bearer.id)
    runtime = _Runtime(
        scenario=scenario,
        entities=entities,
        queues=queues,
        bearers_by_ue={ue_id: tuple(sorted(bearers)) for ue_id, bearers in bearers_by_ue.items()},
        serving_cell_by_ue=serving_cell_by_ue,
        sinr_by_ue=sinr_by_ue,
        full_capacity_by_ue=full_capacity_by_ue,
        scheduler=build_scheduler(scenario.scheduler),
        intervals=[],
    )
    kernel = DeterministicKernel()
    _schedule_exogenous_events(kernel, runtime, packets)
    _schedule_slot_events(kernel, runtime)
    kernel.register_handler(EventKind.PACKET_ARRIVAL, _arrival_handler(runtime))
    kernel.register_handler(EventKind.PACKET_DEADLINE, _deadline_handler(runtime))
    kernel.register_handler(EventKind.SCHEDULING, _scheduling_handler(runtime))
    kernel.register_handler(EventKind.SERVICE_COMPLETION, _service_handler(runtime))
    kernel.register_handler(EventKind.CENSOR_AT_STOP, _censor_handler(runtime))
    trace = kernel.run(scenario.simulation.stop_ns)

    ledgers = tuple((str(bearer_id), queues[bearer_id].ledger()) for bearer_id in sorted(queues))
    snapshots = tuple(
        (str(bearer_id), queues[bearer_id].snapshots()) for bearer_id in sorted(queues)
    )
    rng_streams = _combine_rng_streams(radio_snapshot.rng_streams, traffic_registry.manifest())
    metadata = build_run_metadata(
        identity,
        working_tree_dirty=working_tree_dirty,
        rng_streams=rng_streams,
    )
    intervals = tuple(sorted(runtime.intervals, key=lambda item: (item.start_tick, item.cell_id)))
    kpis = build_kpi_report(
        scenario,
        entities,
        run_id=str(identity.id),
        serving_cells=serving_cell_by_ue,
        packet_snapshots=snapshots,
        intervals=intervals,
    )
    provisional = SimulationResult(
        schema_version=SIMULATION_RESULT_SCHEMA_VERSION,
        semantic_sha256="",
        configuration_manifest=manifest,
        exogenous_configuration_sha256=exogenous_id,
        identity=identity,
        radio_snapshot=radio_snapshot,
        scheduler_policy_id=runtime.scheduler.policy_id,
        trace=trace,
        intervals=intervals,
        kpis=kpis,
        queue_ledgers=ledgers,
        packet_snapshots=snapshots,
        rng_streams=rng_streams,
        source_diagnostics=tuple(sorted(diagnostics, key=lambda item: item.bearer_id)),
        metadata=metadata,
    )
    digest = hashlib.sha256(_semantic_bytes(provisional)).hexdigest()
    return replace(provisional, semantic_sha256=digest)


def _build_traffic_state(
    scenario: NormalizedScenario,
    entities: EntityRegistry,
    registry: SemanticRngRegistry,
) -> tuple[
    dict[BearerId, BearerQueue],
    list[TrafficSourceDiagnostic],
    dict[BearerId, tuple[PacketRecord, ...]],
]:
    queues: dict[BearerId, BearerQueue] = {}
    diagnostics: list[TrafficSourceDiagnostic] = []
    packets: dict[BearerId, tuple[PacketRecord, ...]] = {}
    for bearer in entities.bearers:
        profile = scenario.traffic_profiles[bearer.traffic_profile_id]
        queues[bearer.id] = BearerQueue(
            bearer,
            max_packets=profile.queue.max_packets,
            max_payload_bits=profile.queue.max_payload_bits,
        )
        generator = build_traffic_generator(bearer, profile, registry)
        generated = generator.packets(
            generation_start_tick=0,
            measurement_start_tick=scenario.simulation.measurement_start_ns,
            generation_stop_tick=scenario.simulation.measurement_end_ns,
        )
        packets[bearer.id] = generated
        diagnostics.extend(generator.diagnostics())
    return queues, diagnostics, packets


def _schedule_exogenous_events(
    kernel: DeterministicKernel,
    runtime: _Runtime,
    packets: dict[BearerId, tuple[PacketRecord, ...]],
) -> None:
    for bearer_id in sorted(packets):
        for local_sequence, packet in enumerate(packets[bearer_id]):
            kernel.schedule(
                create_scheduled_event(
                    tick=packet.arrival_tick,
                    phase=EventPhase.PACKET_ARRIVAL,
                    entity_key=str(bearer_id),
                    local_sequence=local_sequence,
                    kind=EventKind.PACKET_ARRIVAL,
                    payload=EnqueuePacket(tick=packet.arrival_tick, packet=packet),
                )
            )
            if packet.deadline_tick is not None:
                kernel.schedule(
                    create_scheduled_event(
                        tick=packet.deadline_tick,
                        phase=EventPhase.DEADLINE_EXPIRATION,
                        entity_key=str(bearer_id),
                        local_sequence=local_sequence,
                        kind=EventKind.PACKET_DEADLINE,
                        payload=ExpirePacket(tick=packet.deadline_tick, packet_id=packet.id),
                    )
                )
        kernel.schedule(
            create_scheduled_event(
                tick=runtime.scenario.simulation.stop_ns,
                phase=EventPhase.OBSERVATION,
                entity_key=str(bearer_id),
                local_sequence=0,
                kind=EventKind.CENSOR_AT_STOP,
                payload=CensorQueue(tick=runtime.scenario.simulation.stop_ns),
            )
        )


def _schedule_slot_events(kernel: DeterministicKernel, runtime: _Runtime) -> None:
    slot_ns = runtime.scenario.radio.slot_duration_ns
    for slot_ordinal, tick in enumerate(range(0, runtime.scenario.simulation.stop_ns, slot_ns)):
        for cell in runtime.entities.cells:
            cell_id = str(cell.id)
            kernel.schedule(
                create_scheduled_event(
                    tick=tick,
                    phase=EventPhase.SCHEDULING,
                    entity_key=cell_id,
                    local_sequence=slot_ordinal,
                    kind=EventKind.SCHEDULING,
                    payload=_SchedulingTick(cell_id=cell_id, slot_ordinal=slot_ordinal),
                )
            )


def _arrival_handler(runtime: _Runtime) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        command = _require_payload(event, EnqueuePacket)
        queue = runtime.queues[command.packet.bearer_id]
        lifecycle = queue.apply(command)
        if isinstance(lifecycle, ServiceResult):
            raise InvariantViolation("arrival command returned a service result")
        terminal = lifecycle[-1].terminal_cause
        return EventResult.create(
            "overflow_drop" if terminal is not None else "enqueued",
            details={
                "packet_id": str(command.packet.id),
                "payload_bits": command.packet.payload_bits,
                "queue_packets": queue.queued_packet_count,
                "queue_bits": queue.queued_payload_bits,
                "terminal_cause": None if terminal is None else terminal.value,
            },
        )

    return handle


def _deadline_handler(runtime: _Runtime) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        command = _require_payload(event, ExpirePacket)
        lifecycle = runtime.queues[BearerId(event.entity_key)].apply(command)
        if isinstance(lifecycle, ServiceResult):
            raise InvariantViolation("deadline command returned a service result")
        return EventResult.create(
            "already_terminal" if not lifecycle else "deadline_expired",
            details={"packet_id": str(command.packet_id)},
        )

    return handle


def _scheduling_handler(runtime: _Runtime) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        scheduling_tick = _require_payload(event, _SchedulingTick)
        cell_id = scheduling_tick.cell_id
        candidates = tuple(
            _candidate(runtime, ue_id)
            for ue_id in sorted(runtime.serving_cell_by_ue)
            if runtime.serving_cell_by_ue[ue_id] == cell_id and _queued_bits(runtime, ue_id) > 0
        )
        observation = SchedulerObservation(
            tick=event.tick,
            interval_ns=runtime.scenario.radio.slot_duration_ns,
            cell_id=cell_id,
            available_prbs=runtime.scenario.radio.prb_count,
            candidates=candidates,
        )
        decision = runtime.scheduler.decide(observation)
        completion_tick = event.tick + runtime.scenario.radio.slot_duration_ns
        plans = tuple(
            _service_plan(runtime, event.tick, completion_tick, allocation.ue_id, allocation.prbs)
            for allocation in decision.allocations
        )
        followup = create_scheduled_event(
            tick=completion_tick,
            phase=EventPhase.PRIOR_SERVICE_COMPLETION,
            entity_key=cell_id,
            local_sequence=scheduling_tick.slot_ordinal,
            kind=EventKind.SERVICE_COMPLETION,
            payload=_SlotServicePlan(
                observation=observation,
                decision=decision,
                completion_tick=completion_tick,
                ue_plans=plans,
            ),
        )
        return EventResult.create(
            "allocation_committed",
            details={
                "allocated_prbs": sum(item.allocated_prbs for item in plans),
                "eligible_ue_ids": tuple(candidate.ue_id for candidate in candidates),
                "policy_id": decision.policy_id,
                "policy_state": tuple(f"{key}={value}" for key, value in decision.state),
                "scheduled_capacity_bits": sum(
                    item.capacity.capacity_bits_per_interval for item in plans
                ),
            },
            followups=(followup,),
        )

    return handle


def _service_handler(runtime: _Runtime) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        plan = _require_payload(event, _SlotServicePlan)
        outcomes: list[AllocationOutcome] = []
        served_by_ue: dict[str, int] = {}
        for ue_plan in plan.ue_plans:
            bearer_services: list[BearerServiceRecord] = []
            for reservation in ue_plan.reservations:
                result = runtime.queues[reservation.bearer_id].complete_reserved_service(
                    reservation
                )
                bearer_services.append(
                    BearerServiceRecord(
                        bearer_id=str(reservation.bearer_id),
                        reserved_bits=reservation.reserved_bits,
                        served_bits=result.consumed_bits,
                    )
                )
            reserved = sum(item.reserved_bits for item in ue_plan.reservations)
            served = sum(item.served_bits for item in bearer_services)
            served_by_ue[ue_plan.ue_id] = served
            capacity_bits = ue_plan.capacity.capacity_bits_per_interval
            outcomes.append(
                AllocationOutcome(
                    ue_id=ue_plan.ue_id,
                    allocated_prbs=ue_plan.allocated_prbs,
                    capacity_state=ue_plan.capacity.state,
                    scheduled_capacity_bits=capacity_bits,
                    reserved_payload_bits=reserved,
                    served_payload_bits=served,
                    unused_capacity_bits=capacity_bits - served,
                    bearer_services=tuple(bearer_services),
                )
            )
        eligible_ids = tuple(candidate.ue_id for candidate in plan.observation.candidates)
        runtime.scheduler.record_service(
            ServiceFeedback(
                cell_id=plan.observation.cell_id,
                completion_tick=event.tick,
                interval_ns=plan.observation.interval_ns,
                eligible_ue_ids=eligible_ids,
                served_bits=tuple(sorted(served_by_ue.items())),
            )
        )
        outage_ids = tuple(
            candidate.ue_id
            for candidate in plan.observation.candidates
            if runtime.full_capacity_by_ue[candidate.ue_id].state != "capacity_available"
        )
        interval = SchedulingIntervalRecord(
            start_tick=plan.observation.tick,
            completion_tick=event.tick,
            cell_id=plan.observation.cell_id,
            available_prbs=plan.observation.available_prbs,
            eligible_ue_ids=eligible_ids,
            outage_ue_ids=outage_ids,
            decision=plan.decision,
            outcomes=tuple(sorted(outcomes, key=lambda item: item.ue_id)),
            policy_state_after_service=runtime.scheduler.state(),
        )
        runtime.intervals.append(interval)
        state_after_service = runtime.scheduler.state()
        return EventResult.create(
            "service_completed",
            details={
                "allocated_prbs": sum(item.allocated_prbs for item in outcomes),
                "served_payload_bits": sum(item.served_payload_bits for item in outcomes),
                "policy_state": tuple(f"{key}={value}" for key, value in state_after_service),
                "unused_capacity_bits": sum(item.unused_capacity_bits for item in outcomes),
            },
        )

    return handle


def _censor_handler(runtime: _Runtime) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        command = _require_payload(event, CensorQueue)
        result = runtime.queues[BearerId(event.entity_key)].apply(command)
        if isinstance(result, ServiceResult):
            raise InvariantViolation("censor command returned a service result")
        return EventResult.create(
            "queue_censored",
            details={"censored_packet_ids": tuple(str(item.packet_id) for item in result)},
        )

    return handle


def _candidate(runtime: _Runtime, ue_id: str) -> SchedulingCandidate:
    capacity = runtime.full_capacity_by_ue[ue_id]
    return SchedulingCandidate(
        ue_id=ue_id,
        queue_payload_bits=_queued_bits(runtime, ue_id),
        achievable_payload_bits=capacity.capacity_bits_per_interval,
        achievable_rate_bps=capacity.capacity_bit_rate_bps,
        sinr_db=runtime.sinr_by_ue[ue_id],
    )


def _queued_bits(runtime: _Runtime, ue_id: str) -> int:
    return sum(
        runtime.queues[bearer_id].queued_payload_bits for bearer_id in runtime.bearers_by_ue[ue_id]
    )


def _service_plan(
    runtime: _Runtime,
    start_tick: int,
    completion_tick: int,
    ue_id: str,
    allocated_prbs: int,
) -> _UeServicePlan:
    capacity = evaluate_capacity(
        runtime.scenario.radio,
        sinr_db=runtime.sinr_by_ue[ue_id],
        allocated_prbs=allocated_prbs,
    )
    capacity_by_bearer = _oldest_packet_first_capacity(
        runtime,
        ue_id,
        capacity.capacity_bits_per_interval,
    )
    reservations = tuple(
        runtime.queues[bearer_id].reserve_service(
            start_tick=start_tick,
            completion_tick=completion_tick,
            capacity_bits=bits,
        )
        for bearer_id, bits in capacity_by_bearer
        if bits > 0
    )
    return _UeServicePlan(
        ue_id=ue_id,
        allocated_prbs=allocated_prbs,
        capacity=capacity,
        reservations=reservations,
    )


def _oldest_packet_first_capacity(
    runtime: _Runtime,
    ue_id: str,
    capacity_bits: int,
) -> tuple[tuple[BearerId, int], ...]:
    candidates = sorted(
        (
            snapshot.packet.arrival_tick,
            str(bearer_id),
            str(snapshot.packet.id),
            bearer_id,
            snapshot.remaining_bits,
        )
        for bearer_id in runtime.bearers_by_ue[ue_id]
        for snapshot in runtime.queues[bearer_id].snapshots()
        if snapshot.terminal_cause is None
    )
    remaining = capacity_bits
    by_bearer: dict[BearerId, int] = defaultdict(int)
    for _, _, _, bearer_id, packet_bits in candidates:
        if remaining == 0:
            break
        selected = min(remaining, packet_bits)
        by_bearer[bearer_id] += selected
        remaining -= selected
    return tuple(sorted(by_bearer.items()))


def _validate_slot_boundaries(scenario: NormalizedScenario) -> None:
    slot = scenario.radio.slot_duration_ns
    boundaries = {
        "measurement_start_ns": scenario.simulation.measurement_start_ns,
        "measurement_end_ns": scenario.simulation.measurement_end_ns,
        "stop_ns": scenario.simulation.stop_ns,
    }
    invalid = {name: value for name, value in boundaries.items() if value % slot}
    if invalid:
        raise InvariantViolation(
            "integrated Tier A simulation boundaries must align to complete NR slots",
            {**invalid, "slot_duration_ns": slot, "requirement": "TIME-002"},
        )


def _combine_rng_streams(
    *groups: tuple[RngStreamRecord, ...],
) -> tuple[RngStreamRecord, ...]:
    combined = tuple(record for group in groups for record in group)
    paths = tuple(record.semantic_path for record in combined)
    if len(set(paths)) != len(paths):
        raise InvariantViolation(
            "radio and traffic RNG manifests contain a duplicate semantic path",
            {"requirement": "EXP-003"},
        )
    return tuple(sorted(combined, key=lambda item: item.semantic_path))


def _require_payload(event: ScheduledEvent, expected: type[PayloadT]) -> PayloadT:
    if not isinstance(event.payload, expected):
        raise InvariantViolation(
            "kernel event payload does not match its registered handler",
            {
                "event_id": str(event.id),
                "expected": expected.__name__,
                "received": type(event.payload).__name__,
            },
        )
    return event.payload


def _snapshot_dict(snapshot: PacketSnapshot) -> dict[str, TraceValue]:
    packet = snapshot.packet
    return {
        "arrival_tick": packet.arrival_tick,
        "bearer_id": str(packet.bearer_id),
        "cohort": packet.cohort.value,
        "completion_tick": snapshot.completion_tick,
        "deadline_tick": packet.deadline_tick,
        "first_service_tick": snapshot.first_service_tick,
        "packet_id": str(packet.id),
        "payload_bits": packet.payload_bits,
        "remaining_bits": snapshot.remaining_bits,
        "terminal_cause": None
        if snapshot.terminal_cause is None
        else snapshot.terminal_cause.value,
        "terminal_tick": snapshot.terminal_tick,
    }


def _semantic_bytes(result: SimulationResult) -> bytes:
    return json.dumps(
        canonicalize_floats(result.semantic_dict()),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
