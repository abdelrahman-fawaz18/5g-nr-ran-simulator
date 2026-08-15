"""Radio-independent traffic/queue mechanics executed by the deterministic kernel."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import TypeVar

from nr_ran_sim.config.normalize import NormalizedScenario
from nr_ran_sim.domain import BearerId, PacketSnapshot, build_entity_registry
from nr_ran_sim.errors import InvariantViolation, RunExecutionError
from nr_ran_sim.experiments.identity import (
    RunIdentity,
    RunMetadata,
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
from nr_ran_sim.traffic.commands import ApplyService, CensorQueue, EnqueuePacket, ExpirePacket
from nr_ran_sim.traffic.queue import BearerQueue, QueueLedger, ServiceResult
from nr_ran_sim.traffic.sources import (
    TrafficSourceDiagnostic,
    build_traffic_generator,
)

PayloadT = TypeVar("PayloadT")


@dataclass(frozen=True, slots=True)
class ServiceGrant:
    """Capacity realized at a tick and supplied by the policy/radio pipeline."""

    bearer_id: BearerId
    tick: int
    capacity_bits: int

    def __post_init__(self) -> None:
        if self.tick < 0 or self.capacity_bits < 0:
            raise InvariantViolation(
                "service grant tick and capacity must be nonnegative",
                {
                    "bearer_id": str(self.bearer_id),
                    "tick": self.tick,
                    "capacity_bits": self.capacity_bits,
                    "requirement": "MAC-009",
                },
            )


@dataclass(frozen=True, slots=True)
class TrafficMechanicsResult:
    identity: RunIdentity
    trace: SemanticTrace
    queue_ledgers: tuple[tuple[str, QueueLedger], ...]
    packet_snapshots: tuple[tuple[str, tuple[PacketSnapshot, ...]], ...]
    rng_streams: tuple[RngStreamRecord, ...]
    source_diagnostics: tuple[TrafficSourceDiagnostic, ...]
    metadata: RunMetadata

    def semantic_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity.as_dict(),
            "packet_snapshots": {
                bearer_id: [_snapshot_dict(snapshot) for snapshot in snapshots]
                for bearer_id, snapshots in self.packet_snapshots
            },
            "queue_ledgers": {
                bearer_id: asdict(ledger) for bearer_id, ledger in self.queue_ledgers
            },
            "rng_streams": [asdict(record) for record in self.rng_streams],
            "source_diagnostics": [asdict(item) for item in self.source_diagnostics],
            "trace": self.trace.as_dict(),
        }

    def to_semantic_json(self) -> str:
        return (
            json.dumps(
                self.semantic_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        )

    @property
    def semantic_sha256(self) -> str:
        return hashlib.sha256(self.to_semantic_json().encode("utf-8")).hexdigest()


def run_traffic_mechanics(
    scenario: NormalizedScenario,
    *,
    configuration_sha256: str,
    master_seed: str,
    replication_id: int,
    code_revision: str,
    working_tree_dirty: bool,
    service_grants: tuple[ServiceGrant, ...] = (),
) -> TrafficMechanicsResult:
    """Execute traffic and queue mechanics without claiming radio/scheduler behavior."""

    model_profiles = {str(key): str(value) for key, value in scenario.models.model_dump().items()}
    identity = build_run_identity(
        configuration_sha256=configuration_sha256,
        master_seed=master_seed,
        replication_id=replication_id,
        code_revision=code_revision,
        model_profiles=model_profiles,
    )
    rng_registry = SemanticRngRegistry(configuration_sha256, master_seed, replication_id)
    entities = build_entity_registry(scenario)
    queues: dict[BearerId, BearerQueue] = {}
    diagnostics: list[TrafficSourceDiagnostic] = []
    kernel = DeterministicKernel()

    for bearer in entities.bearers:
        profile = scenario.traffic_profiles[bearer.traffic_profile_id]
        queue = BearerQueue(
            bearer,
            max_packets=profile.queue.max_packets,
            max_payload_bits=profile.queue.max_payload_bits,
        )
        queues[bearer.id] = queue
        generator = build_traffic_generator(bearer, profile, rng_registry)
        packets = generator.packets(
            generation_start_tick=0,
            measurement_start_tick=scenario.simulation.measurement_start_ns,
            generation_stop_tick=scenario.simulation.measurement_end_ns,
        )
        diagnostics.extend(generator.diagnostics())
        for local_sequence, packet in enumerate(packets):
            kernel.schedule(
                create_scheduled_event(
                    tick=packet.arrival_tick,
                    phase=EventPhase.PACKET_ARRIVAL,
                    entity_key=str(bearer.id),
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
                        entity_key=str(bearer.id),
                        local_sequence=local_sequence,
                        kind=EventKind.PACKET_DEADLINE,
                        payload=ExpirePacket(
                            tick=packet.deadline_tick,
                            packet_id=packet.id,
                        ),
                    )
                )
        kernel.schedule(
            create_scheduled_event(
                tick=scenario.simulation.stop_ns,
                phase=EventPhase.OBSERVATION,
                entity_key=str(bearer.id),
                local_sequence=0,
                kind=EventKind.CENSOR_AT_STOP,
                payload=CensorQueue(tick=scenario.simulation.stop_ns),
            )
        )

    _schedule_service_grants(
        kernel,
        queues,
        service_grants,
        stop_tick=scenario.simulation.stop_ns,
        slot_duration_ns=scenario.radio.slot_duration_ns,
    )
    kernel.register_handler(EventKind.PACKET_ARRIVAL, _arrival_handler(queues))
    kernel.register_handler(EventKind.PACKET_DEADLINE, _deadline_handler(queues))
    kernel.register_handler(EventKind.SERVICE_COMPLETION, _service_handler(queues))
    kernel.register_handler(EventKind.CENSOR_AT_STOP, _censor_handler(queues))
    trace = kernel.run(scenario.simulation.stop_ns)

    ledgers = tuple((str(bearer_id), queues[bearer_id].ledger()) for bearer_id in sorted(queues))
    snapshots = tuple(
        (str(bearer_id), queues[bearer_id].snapshots()) for bearer_id in sorted(queues)
    )
    rng_streams = rng_registry.manifest()
    metadata = build_run_metadata(
        identity,
        working_tree_dirty=working_tree_dirty,
        rng_streams=rng_streams,
    )
    return TrafficMechanicsResult(
        identity=identity,
        trace=trace,
        queue_ledgers=ledgers,
        packet_snapshots=snapshots,
        rng_streams=rng_streams,
        source_diagnostics=tuple(sorted(diagnostics, key=lambda item: item.bearer_id)),
        metadata=metadata,
    )


def _schedule_service_grants(
    kernel: DeterministicKernel,
    queues: dict[BearerId, BearerQueue],
    grants: tuple[ServiceGrant, ...],
    *,
    stop_tick: int,
    slot_duration_ns: int,
) -> None:
    aggregated: dict[tuple[int, BearerId], int] = {}
    for grant in grants:
        if grant.bearer_id not in queues:
            raise RunExecutionError(
                "service grant references an unknown bearer",
                {"bearer_id": str(grant.bearer_id)},
            )
        if grant.tick > stop_tick:
            raise RunExecutionError(
                "service grant occurs after the configured simulation stop",
                {"tick": grant.tick, "stop_tick": stop_tick},
            )
        if grant.tick % slot_duration_ns:
            raise RunExecutionError(
                "service completion must occur on a configured slot boundary",
                {
                    "tick": grant.tick,
                    "slot_duration_ns": slot_duration_ns,
                    "requirement": "TIME-002",
                },
            )
        key = (grant.tick, grant.bearer_id)
        aggregated[key] = aggregated.get(key, 0) + grant.capacity_bits
    for (tick, bearer_id), capacity_bits in sorted(
        aggregated.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        kernel.schedule(
            create_scheduled_event(
                tick=tick,
                phase=EventPhase.PRIOR_SERVICE_COMPLETION,
                entity_key=str(bearer_id),
                local_sequence=0,
                kind=EventKind.SERVICE_COMPLETION,
                payload=ApplyService(tick=tick, capacity_bits=capacity_bits),
            )
        )


def _arrival_handler(
    queues: dict[BearerId, BearerQueue],
) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        command = _require_payload(event, EnqueuePacket)
        queue = queues[command.packet.bearer_id]
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


def _deadline_handler(
    queues: dict[BearerId, BearerQueue],
) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        command = _require_payload(event, ExpirePacket)
        bearer_id = BearerId(event.entity_key)
        lifecycle = queues[bearer_id].apply(command)
        if isinstance(lifecycle, ServiceResult):
            raise InvariantViolation("deadline command returned a service result")
        return EventResult.create(
            "already_terminal" if not lifecycle else "deadline_expired",
            details={"packet_id": str(command.packet_id)},
        )

    return handle


def _service_handler(
    queues: dict[BearerId, BearerQueue],
) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        command = _require_payload(event, ApplyService)
        result = queues[BearerId(event.entity_key)].apply(command)
        if not isinstance(result, ServiceResult):
            raise InvariantViolation("service command did not return a service result")
        completed = tuple(
            str(item.packet_id) for item in result.events if item.terminal_cause is not None
        )
        return EventResult.create(
            "service_applied",
            details={
                "completed_packet_ids": completed,
                "consumed_bits": result.consumed_bits,
                "requested_bits": result.requested_bits,
                "unused_bits": result.unused_bits,
            },
        )

    return handle


def _censor_handler(
    queues: dict[BearerId, BearerQueue],
) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        command = _require_payload(event, CensorQueue)
        result = queues[BearerId(event.entity_key)].apply(command)
        if isinstance(result, ServiceResult):
            raise InvariantViolation("censor command returned a service result")
        return EventResult.create(
            "queue_censored",
            details={"censored_packet_ids": tuple(str(item.packet_id) for item in result)},
        )

    return handle


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
        "terminal_cause": (
            None if snapshot.terminal_cause is None else snapshot.terminal_cause.value
        ),
        "terminal_tick": snapshot.terminal_tick,
    }
