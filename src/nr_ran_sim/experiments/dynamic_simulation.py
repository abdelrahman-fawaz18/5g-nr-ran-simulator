"""Integrated opt-in mobility, activity interference, and availability simulation."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, TypeVar, cast

from nr_ran_sim.config.dynamic import NormalizedDynamicRadio, load_normalized_dynamic_radio
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
from nr_ran_sim.experiments.seeds import OwnedRng, RngStreamRecord, SemanticRngRegistry
from nr_ran_sim.experiments.simulation import _build_traffic_state
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
    MetricRecord,
    SchedulingIntervalRecord,
    build_kpi_report,
)
from nr_ran_sim.radio.capacity import CapacityResult, evaluate_capacity
from nr_ran_sim.radio.dynamic import (
    ActivitySinrResult,
    AvailabilityState,
    AvailabilityTransition,
    BeamSelection,
    BlockageState,
    HandoverState,
    HandoverTransition,
    MotionState,
    Velocity3D,
    advance_linear_reflect,
    calculate_activity_coupled_sinr,
    evolve_correlated_shadow,
    explicit_blockage_state,
    select_horizontal_beam,
    update_availability_state,
    update_handover_state,
)
from nr_ran_sim.radio.geometry import LinkGeometry, Position3D, link_geometry
from nr_ran_sim.radio.link import LinkBudgetResult, calculate_link_budget
from nr_ran_sim.radio.propagation import (
    TR38901_MAXIMUM_CARRIER_HZ,
    LosSelectionResult,
    PathLossResult,
    PropagationState,
    Scenario,
    evaluate_path_loss,
    select_los_state,
)
from nr_ran_sim.radio.snapshot import canonicalize_floats
from nr_ran_sim.radio.topology import RadioCell, RadioTopology, RadioUe, build_radio_topology
from nr_ran_sim.traffic.commands import CensorQueue, EnqueuePacket, ExpirePacket
from nr_ran_sim.traffic.queue import BearerQueue, QueueLedger, ServiceReservation, ServiceResult
from nr_ran_sim.traffic.sources import TrafficSourceDiagnostic

DYNAMIC_RESULT_SCHEMA_VERSION = "1.0"
DYNAMIC_KPI_DEFINITION_VERSION = "dynamic-radio-1.0"
PayloadT = TypeVar("PayloadT")


@dataclass(frozen=True, slots=True)
class DynamicLinkObservation:
    cell_id: str
    ue_id: str
    geometry: LinkGeometry
    los_selection: LosSelectionResult
    path_loss: PathLossResult
    beam: BeamSelection | None
    blockage: BlockageState | None
    link_budget: LinkBudgetResult

    def as_dict(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "ue_id": self.ue_id,
            "geometry": self.geometry.as_dict(),
            "los_selection": self.los_selection.as_dict(),
            "path_loss": self.path_loss.as_dict(),
            "beam": None if self.beam is None else self.beam.as_dict(),
            "blockage": None if self.blockage is None else self.blockage.as_dict(),
            "link_budget": self.link_budget.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class DynamicUeFrame:
    ue_id: str
    position: Position3D
    velocity: Velocity3D
    serving_cell_id: str
    sinr: ActivitySinrResult
    handover_state: HandoverState
    availability_state: AvailabilityState
    available_for_scheduling: bool
    outage: bool
    handover_interruption: bool
    links: tuple[DynamicLinkObservation, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ue_id": self.ue_id,
            "position": self.position.as_dict(),
            "velocity": self.velocity.as_dict(),
            "serving_cell_id": self.serving_cell_id,
            "sinr": self.sinr.as_dict(),
            "handover_state": self.handover_state.as_dict(),
            "availability_state": self.availability_state.as_dict(),
            "available_for_scheduling": self.available_for_scheduling,
            "outage": self.outage,
            "handover_interruption": self.handover_interruption,
            "links": [item.as_dict() for item in self.links],
        }


@dataclass(frozen=True, slots=True)
class DynamicRadioFrame:
    tick: int
    channel_updated: bool
    previous_active_prbs: tuple[tuple[str, int], ...]
    ue_states: tuple[DynamicUeFrame, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "tick": self.tick,
            "channel_updated": self.channel_updated,
            "previous_active_prbs": dict(self.previous_active_prbs),
            "ue_states": [item.as_dict() for item in self.ue_states],
        }


@dataclass(frozen=True, slots=True)
class DynamicAllocationRadioDiagnostic:
    start_tick: int
    cell_id: str
    ue_id: str
    allocated_prbs: int
    sinr: ActivitySinrResult

    def as_dict(self) -> dict[str, object]:
        return {
            "start_tick": self.start_tick,
            "cell_id": self.cell_id,
            "ue_id": self.ue_id,
            "allocated_prbs": self.allocated_prbs,
            "sinr": self.sinr.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class DynamicSimulationResult:
    schema_version: str
    semantic_sha256: str
    configuration_manifest: ManifestEnvelope
    exogenous_configuration_sha256: str
    identity: RunIdentity
    initial_topology: RadioTopology
    scheduler_policy_id: str
    trace: SemanticTrace
    radio_frames: tuple[DynamicRadioFrame, ...]
    allocation_radio_diagnostics: tuple[DynamicAllocationRadioDiagnostic, ...]
    handover_transitions: tuple[HandoverTransition, ...]
    availability_transitions: tuple[AvailabilityTransition, ...]
    intervals: tuple[SchedulingIntervalRecord, ...]
    kpis: KpiReport
    dynamic_kpis: KpiReport
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
            "initial_topology": self.initial_topology.as_dict(),
            "scheduler_policy_id": self.scheduler_policy_id,
            "trace": self.trace.as_dict(),
            "radio_frames": [item.as_dict() for item in self.radio_frames],
            "allocation_radio_diagnostics": [
                item.as_dict() for item in self.allocation_radio_diagnostics
            ],
            "handover_transitions": [item.as_dict() for item in self.handover_transitions],
            "availability_transitions": [item.as_dict() for item in self.availability_transitions],
            "intervals": [item.as_dict() for item in self.intervals],
            "kpis": self.kpis.as_dict(),
            "dynamic_kpis": self.dynamic_kpis.as_dict(),
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
                "output dynamic simulation result already exists; pass --force to replace it",
                {"path": str(path)},
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_text(self.to_json(), encoding="utf-8", newline="\n")
            temporary.replace(path)
        except OSError as exc:
            raise ArtifactError(
                "unable to commit dynamic simulation result",
                {"path": str(path), "detail": str(exc)},
            ) from exc
        finally:
            if temporary.exists():
                temporary.unlink()


@dataclass(frozen=True, slots=True)
class _TopologyTick:
    slot_ordinal: int


@dataclass(frozen=True, slots=True)
class _AssociationTick:
    slot_ordinal: int


@dataclass(frozen=True, slots=True)
class _SchedulingTick:
    cell_id: str
    slot_ordinal: int


@dataclass(frozen=True, slots=True)
class _UeServicePlan:
    ue_id: str
    allocated_prbs: int
    sinr: ActivitySinrResult
    capacity: CapacityResult
    reservations: tuple[ServiceReservation, ...]


@dataclass(frozen=True, slots=True)
class _SlotServicePlan:
    observation: SchedulerObservation
    decision: AllocationDecision
    completion_tick: int
    ue_plans: tuple[_UeServicePlan, ...]


@dataclass(slots=True)
class _LinkState:
    los: LosSelectionResult
    shadow_db: float
    shadow_rng: OwnedRng | None


@dataclass(slots=True)
class _Runtime:
    scenario: NormalizedScenario
    dynamic: NormalizedDynamicRadio
    entities: EntityRegistry
    topology: RadioTopology
    queues: dict[BearerId, BearerQueue]
    bearers_by_ue: dict[str, tuple[BearerId, ...]]
    scheduler: SchedulerPolicy
    radio_registry: SemanticRngRegistry
    motion: dict[str, MotionState]
    link_state: dict[tuple[str, str], _LinkState]
    links_by_ue: dict[str, tuple[DynamicLinkObservation, ...]]
    handover: dict[str, HandoverState]
    availability: dict[str, AvailabilityState]
    sinr_by_ue: dict[str, ActivitySinrResult]
    full_capacity_by_ue: dict[str, CapacityResult]
    previous_active_prbs: dict[str, int]
    current_active_prbs: dict[str, int]
    channel_updated: bool
    frames: list[DynamicRadioFrame]
    allocation_radio_diagnostics: list[DynamicAllocationRadioDiagnostic]
    handover_transitions: list[HandoverTransition]
    availability_transitions: list[AvailabilityTransition]
    intervals: list[SchedulingIntervalRecord]


def run_dynamic_system_simulation(
    scenario: NormalizedScenario,
    *,
    master_seed: str,
    replication_id: int,
    code_revision: str,
    working_tree_dirty: bool,
    experiment_factors: dict[str, str] | None = None,
) -> DynamicSimulationResult:
    """Run the declared dynamic profile through the deterministic event kernel."""

    dynamic = load_normalized_dynamic_radio(scenario.extensions)
    if dynamic is None or scenario.models.fidelity_profile == "tier-a-fr1-static-v1":
        raise InvariantViolation(
            "dynamic simulation requires an opt-in dynamic-radio fidelity profile",
            {"requirement": "DYN-REP-001"},
        )
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
            "dynamic_kpi_definition": DYNAMIC_KPI_DEFINITION_VERSION,
        },
        experiment_factors=(
            {"scheduler_policy": scenario.scheduler.policy}
            if experiment_factors is None
            else experiment_factors
        ),
    )
    radio_registry = SemanticRngRegistry(exogenous_id, master_seed, replication_id)
    topology = build_radio_topology(scenario, radio_registry)
    entities = build_entity_registry(scenario)
    traffic_registry = SemanticRngRegistry(exogenous_id, master_seed, replication_id)
    queues, diagnostics, packets = _build_traffic_state(scenario, entities, traffic_registry)
    bearers_by_ue: dict[str, list[BearerId]] = defaultdict(list)
    for bearer in entities.bearers:
        bearers_by_ue[str(bearer.ue_id)].append(bearer.id)
    motion = {
        ue.id: MotionState(
            ue.position,
            Velocity3D(
                float(dynamic.mobility_groups[ue.group_id].velocities[ue.ordinal].x_mps),
                float(dynamic.mobility_groups[ue.group_id].velocities[ue.ordinal].y_mps),
                0.0,
            ),
        )
        for ue in topology.ues
    }
    cell_ids = tuple(cell.id for cell in topology.cells)
    runtime = _Runtime(
        scenario=scenario,
        dynamic=dynamic,
        entities=entities,
        topology=topology,
        queues=queues,
        bearers_by_ue={key: tuple(sorted(value)) for key, value in bearers_by_ue.items()},
        scheduler=build_scheduler(scenario.scheduler),
        radio_registry=radio_registry,
        motion=motion,
        link_state={},
        links_by_ue={},
        handover={},
        availability={ue.id: AvailabilityState() for ue in topology.ues},
        sinr_by_ue={},
        full_capacity_by_ue={},
        previous_active_prbs=dict.fromkeys(cell_ids, dynamic.channel.initial_active_prbs),
        current_active_prbs=dict.fromkeys(cell_ids, 0),
        channel_updated=False,
        frames=[],
        allocation_radio_diagnostics=[],
        handover_transitions=[],
        availability_transitions=[],
        intervals=[],
    )
    kernel = DeterministicKernel()
    _schedule_events(kernel, runtime, packets)
    kernel.register_handler(EventKind.TOPOLOGY_CONTROL, _topology_handler(runtime))
    kernel.register_handler(EventKind.PACKET_ARRIVAL, _arrival_handler(runtime))
    kernel.register_handler(EventKind.PACKET_DEADLINE, _deadline_handler(runtime))
    kernel.register_handler(EventKind.LINK_ASSOCIATION, _association_handler(runtime))
    kernel.register_handler(EventKind.SCHEDULING, _scheduling_handler(runtime))
    kernel.register_handler(EventKind.SERVICE_COMPLETION, _service_handler(runtime))
    kernel.register_handler(EventKind.CENSOR_AT_STOP, _censor_handler(runtime))
    trace = kernel.run(scenario.simulation.stop_ns)

    ledgers = tuple((str(key), queues[key].ledger()) for key in sorted(queues))
    snapshots = tuple((str(key), queues[key].snapshots()) for key in sorted(queues))
    streams = _combine_rng_streams(radio_registry.manifest(), traffic_registry.manifest())
    metadata = build_run_metadata(
        identity, working_tree_dirty=working_tree_dirty, rng_streams=streams
    )
    intervals = tuple(sorted(runtime.intervals, key=lambda item: (item.start_tick, item.cell_id)))
    serving_cells = {ue_id: state.serving_cell_id for ue_id, state in runtime.handover.items()}
    base_kpis = build_kpi_report(
        scenario,
        entities,
        run_id=str(identity.id),
        serving_cells=serving_cells,
        packet_snapshots=snapshots,
        intervals=intervals,
    )
    valid_dynamic_cell_metrics = {
        "scheduled_capacity_bps",
        "prb_utilization",
        "wasted_allocation_ratio",
        "payload_spectral_efficiency_bit_per_s_per_hz",
    }
    kpis = KpiReport(
        base_kpis.definition_version,
        tuple(
            record
            for record in base_kpis.records
            if record.aggregation_level != "cell" or record.name in valid_dynamic_cell_metrics
        ),
    )
    provisional = DynamicSimulationResult(
        schema_version=DYNAMIC_RESULT_SCHEMA_VERSION,
        semantic_sha256="",
        configuration_manifest=manifest,
        exogenous_configuration_sha256=exogenous_id,
        identity=identity,
        initial_topology=topology,
        scheduler_policy_id=runtime.scheduler.policy_id,
        trace=trace,
        radio_frames=tuple(runtime.frames),
        allocation_radio_diagnostics=tuple(runtime.allocation_radio_diagnostics),
        handover_transitions=tuple(runtime.handover_transitions),
        availability_transitions=tuple(runtime.availability_transitions),
        intervals=intervals,
        kpis=kpis,
        dynamic_kpis=_build_dynamic_kpis(runtime, str(identity.id)),
        queue_ledgers=ledgers,
        packet_snapshots=snapshots,
        rng_streams=streams,
        source_diagnostics=tuple(sorted(diagnostics, key=lambda item: item.bearer_id)),
        metadata=metadata,
    )
    digest = hashlib.sha256(_semantic_bytes(provisional.semantic_dict())).hexdigest()
    return replace(provisional, semantic_sha256=digest)


def _schedule_events(
    kernel: DeterministicKernel,
    runtime: _Runtime,
    packets: dict[BearerId, tuple[PacketRecord, ...]],
) -> None:
    for bearer_id in sorted(packets):
        for sequence, packet in enumerate(packets[bearer_id]):
            kernel.schedule(
                create_scheduled_event(
                    tick=packet.arrival_tick,
                    phase=EventPhase.PACKET_ARRIVAL,
                    entity_key=str(bearer_id),
                    local_sequence=sequence,
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
                        local_sequence=sequence,
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
    slot_ns = runtime.scenario.radio.slot_duration_ns
    for ordinal, tick in enumerate(range(0, runtime.scenario.simulation.stop_ns, slot_ns)):
        kernel.schedule(
            create_scheduled_event(
                tick=tick,
                phase=EventPhase.TOPOLOGY_CONTROL,
                entity_key="system/dynamic-radio",
                local_sequence=ordinal,
                kind=EventKind.TOPOLOGY_CONTROL,
                payload=_TopologyTick(ordinal),
            )
        )
        kernel.schedule(
            create_scheduled_event(
                tick=tick,
                phase=EventPhase.LINK_ASSOCIATION,
                entity_key="system/dynamic-radio",
                local_sequence=ordinal,
                kind=EventKind.LINK_ASSOCIATION,
                payload=_AssociationTick(ordinal),
            )
        )
        for cell in runtime.topology.cells:
            kernel.schedule(
                create_scheduled_event(
                    tick=tick,
                    phase=EventPhase.SCHEDULING,
                    entity_key=cell.id,
                    local_sequence=ordinal,
                    kind=EventKind.SCHEDULING,
                    payload=_SchedulingTick(cell.id, ordinal),
                )
            )


def _topology_handler(runtime: _Runtime) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        _require_payload(event, _TopologyTick)
        if event.tick > 0:
            runtime.previous_active_prbs = dict(runtime.current_active_prbs)
        runtime.current_active_prbs = {cell.id: 0 for cell in runtime.topology.cells}
        update = event.tick % runtime.dynamic.channel.update_interval_ns == 0
        runtime.channel_updated = update
        elapsed = 0 if event.tick == 0 or not update else runtime.dynamic.channel.update_interval_ns
        if update:
            for ue in runtime.topology.ues:
                group = runtime.dynamic.mobility_groups[ue.group_id]
                runtime.motion[ue.id] = advance_linear_reflect(
                    runtime.motion[ue.id], group.bounds, elapsed
                )
        runtime.links_by_ue = {
            ue.id: tuple(
                _evaluate_link(runtime, cell, ue, event.tick, elapsed)
                for cell in runtime.topology.cells
            )
            for ue in runtime.topology.ues
        }
        return EventResult.create(
            "dynamic_links_updated",
            details={
                "channel_updated": update,
                "link_count": sum(map(len, runtime.links_by_ue.values())),
            },
        )

    return handle


def _association_handler(runtime: _Runtime) -> Callable[[ScheduledEvent], EventResult]:
    def handle(event: ScheduledEvent) -> EventResult:
        _require_payload(event, _AssociationTick)
        frames: list[DynamicUeFrame] = []
        available_count = 0
        for ue in runtime.topology.ues:
            links = runtime.links_by_ue[ue.id]
            measurements = {
                item.cell_id: item.link_budget.reference_signal_received_power_dbm for item in links
            }
            if ue.id not in runtime.handover:
                serving = sorted(measurements.items(), key=lambda item: (-item[1], item[0]))[0][0]
                runtime.handover[ue.id] = HandoverState(serving)
            else:
                state, handover_transition = update_handover_state(
                    runtime.handover[ue.id],
                    tick=event.tick,
                    ue_id=ue.id,
                    measurements_dbm=measurements,
                    config=runtime.dynamic.handover,
                )
                runtime.handover[ue.id] = state
                if handover_transition is not None:
                    runtime.handover_transitions.append(handover_transition)
            handover = runtime.handover[ue.id]
            serving_link = next(item for item in links if item.cell_id == handover.serving_cell_id)
            sinr = calculate_activity_coupled_sinr(
                serving_link.link_budget,
                tuple(item.link_budget for item in links),
                allocated_prbs=runtime.scenario.radio.prb_count,
                available_prbs=runtime.scenario.radio.prb_count,
                previous_active_prbs=runtime.previous_active_prbs,
                receiver_noise_figure_db=ue.receiver_noise_figure_db,
            )
            availability, availability_transition = update_availability_state(
                runtime.availability[ue.id],
                tick=event.tick,
                ue_id=ue.id,
                sinr_db=sinr.sinr_db,
                config=runtime.dynamic.availability,
            )
            runtime.availability[ue.id] = availability
            if availability_transition is not None:
                runtime.availability_transitions.append(availability_transition)
            interrupted = event.tick < handover.interruption_until_tick
            available = not availability.outage and not interrupted
            available_count += int(available)
            runtime.sinr_by_ue[ue.id] = sinr
            runtime.full_capacity_by_ue[ue.id] = evaluate_capacity(
                runtime.scenario.radio,
                sinr_db=sinr.sinr_db,
                allocated_prbs=runtime.scenario.radio.prb_count,
            )
            frames.append(
                DynamicUeFrame(
                    ue_id=ue.id,
                    position=runtime.motion[ue.id].position,
                    velocity=runtime.motion[ue.id].velocity,
                    serving_cell_id=handover.serving_cell_id,
                    sinr=sinr,
                    handover_state=handover,
                    availability_state=availability,
                    available_for_scheduling=available,
                    outage=availability.outage,
                    handover_interruption=interrupted,
                    links=links,
                )
            )
        runtime.frames.append(
            DynamicRadioFrame(
                tick=event.tick,
                channel_updated=runtime.channel_updated,
                previous_active_prbs=tuple(sorted(runtime.previous_active_prbs.items())),
                ue_states=tuple(sorted(frames, key=lambda item: item.ue_id)),
            )
        )
        return EventResult.create(
            "association_availability_updated",
            details={"available_ue_count": available_count, "ue_count": len(frames)},
        )

    return handle


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
        scheduling = _require_payload(event, _SchedulingTick)
        candidates = tuple(
            _candidate(runtime, ue.id)
            for ue in runtime.topology.ues
            if runtime.handover[ue.id].serving_cell_id == scheduling.cell_id
            and _is_available(runtime, ue.id, event.tick)
            and _queued_bits(runtime, ue.id) > 0
        )
        observation = SchedulerObservation(
            tick=event.tick,
            interval_ns=runtime.scenario.radio.slot_duration_ns,
            cell_id=scheduling.cell_id,
            available_prbs=runtime.scenario.radio.prb_count,
            candidates=tuple(sorted(candidates, key=lambda item: item.ue_id)),
        )
        decision = runtime.scheduler.decide(observation)
        completion = event.tick + runtime.scenario.radio.slot_duration_ns
        plans = tuple(
            _service_plan(runtime, event.tick, completion, item.ue_id, item.prbs)
            for item in decision.allocations
        )
        runtime.allocation_radio_diagnostics.extend(
            DynamicAllocationRadioDiagnostic(
                start_tick=event.tick,
                cell_id=scheduling.cell_id,
                ue_id=item.ue_id,
                allocated_prbs=item.allocated_prbs,
                sinr=item.sinr,
            )
            for item in plans
        )
        runtime.current_active_prbs[scheduling.cell_id] = sum(item.allocated_prbs for item in plans)
        followup = create_scheduled_event(
            tick=completion,
            phase=EventPhase.PRIOR_SERVICE_COMPLETION,
            entity_key=scheduling.cell_id,
            local_sequence=scheduling.slot_ordinal,
            kind=EventKind.SERVICE_COMPLETION,
            payload=_SlotServicePlan(observation, decision, completion, plans),
        )
        return EventResult.create(
            "allocation_committed",
            details={
                "allocated_prbs": runtime.current_active_prbs[scheduling.cell_id],
                "eligible_ue_ids": tuple(item.ue_id for item in observation.candidates),
                "policy_id": decision.policy_id,
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
            reserved = sum(item.reserved_bits for item in bearer_services)
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
        eligible = tuple(item.ue_id for item in plan.observation.candidates)
        runtime.scheduler.record_service(
            ServiceFeedback(
                cell_id=plan.observation.cell_id,
                completion_tick=event.tick,
                interval_ns=plan.observation.interval_ns,
                eligible_ue_ids=eligible,
                served_bits=tuple(sorted(served_by_ue.items())),
            )
        )
        runtime.intervals.append(
            SchedulingIntervalRecord(
                start_tick=plan.observation.tick,
                completion_tick=event.tick,
                cell_id=plan.observation.cell_id,
                available_prbs=plan.observation.available_prbs,
                eligible_ue_ids=eligible,
                outage_ue_ids=tuple(
                    item.ue_id
                    for item in plan.observation.candidates
                    if runtime.full_capacity_by_ue[item.ue_id].state != "capacity_available"
                ),
                decision=plan.decision,
                outcomes=tuple(sorted(outcomes, key=lambda item: item.ue_id)),
                policy_state_after_service=runtime.scheduler.state(),
            )
        )
        return EventResult.create(
            "service_completed",
            details={"served_payload_bits": sum(item.served_payload_bits for item in outcomes)},
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


def _evaluate_link(
    runtime: _Runtime,
    cell: RadioCell,
    ue: RadioUe,
    tick: int,
    elapsed_ns: int,
) -> DynamicLinkObservation:
    position = runtime.motion[ue.id].position
    moving_ue = replace(ue, position=position)
    geometry = link_geometry(cell.position, position)
    key = (cell.id, ue.id)
    if key not in runtime.link_state:
        explicit = _explicit_state(runtime.scenario, cell.configuration_id, ue)
        los_rng = (
            None
            if runtime.scenario.models.los_state == "explicit"
            else runtime.radio_registry.acquire(
                f"link/{cell.configuration_id}/{ue.id}/los",
                owner=f"dynamic-los:{cell.id}:{ue.id}",
            )
        )
        los = select_los_state(
            cast(Scenario, runtime.scenario.topology.scenario),
            geometry.horizontal_distance_m,
            position.z_m,
            mode=cast(Literal["explicit", "probability_static"], runtime.scenario.models.los_state),
            explicit_state=explicit,
            rng=los_rng,
        )
        shadow_rng = (
            runtime.radio_registry.acquire(
                f"link/{cell.configuration_id}/{ue.id}/shadow-evolution",
                owner=f"dynamic-shadow:{cell.id}:{ue.id}",
            )
            if runtime.scenario.models.shadowing == "correlated_dynamic"
            else None
        )
        runtime.link_state[key] = _LinkState(los=los, shadow_db=0.0, shadow_rng=shadow_rng)
    state = runtime.link_state[key]
    path_loss = evaluate_path_loss(
        cast(Scenario, runtime.scenario.topology.scenario),
        state.los.state,
        geometry,
        float(runtime.scenario.radio.carrier_frequency_hz),
        effective_environment_height_m=1.0,
        average_building_height_m=(
            None
            if runtime.scenario.topology.average_building_height_m is None
            else float(runtime.scenario.topology.average_building_height_m)
        ),
        average_street_width_m=(
            None
            if runtime.scenario.topology.average_street_width_m is None
            else float(runtime.scenario.topology.average_street_width_m)
        ),
        maximum_carrier_hz=TR38901_MAXIMUM_CARRIER_HZ,
    )
    if state.shadow_rng is not None and runtime.channel_updated:
        if tick == 0:
            state.shadow_db = state.shadow_rng.normal(0.0, path_loss.shadow_standard_deviation_db)
        else:
            correlation = runtime.dynamic.channel.shadow_correlation_distance_m
            if correlation is None:
                raise InvariantViolation(
                    "correlated shadowing requires a normalized correlation distance",
                    {"requirement": "DYN-CH-003"},
                )
            speed = math.hypot(
                runtime.motion[ue.id].velocity.x_mps, runtime.motion[ue.id].velocity.y_mps
            )
            evolved = evolve_correlated_shadow(
                state.shadow_db,
                sigma_db=path_loss.shadow_standard_deviation_db,
                travelled_distance_m=speed * elapsed_ns / 1_000_000_000,
                correlation_distance_m=float(correlation),
                innovation_standard_normal=state.shadow_rng.normal(0.0, 1.0),
            )
            state.shadow_db = evolved.value_db
    path_loss = path_loss.with_shadow(state.shadow_db)
    beam: BeamSelection | None = None
    blockage: BlockageState | None = None
    adjusted_cell = cell
    adjusted_ue = moving_ue
    if runtime.dynamic.fr2 is not None:
        beam = select_horizontal_beam(
            cell.position,
            position,
            runtime.dynamic.fr2.beam_codebooks[cell.configuration_id],
        )
        blockage = explicit_blockage_state(
            tick=tick,
            ue_id=ue.id,
            cell_id=cell.id,
            intervals=runtime.dynamic.fr2.blockage_intervals,
        )
        adjusted_cell = replace(cell, antenna_gain_dbi=cell.antenna_gain_dbi + beam.gain_db)
        adjusted_ue = replace(
            moving_ue,
            penetration_loss_db=moving_ue.penetration_loss_db + blockage.excess_loss_db,
        )
    budget = calculate_link_budget(
        adjusted_cell,
        adjusted_ue,
        path_loss,
        transmission_bandwidth_hz=runtime.scenario.radio.transmission_bandwidth_hz,
        subcarrier_spacing_hz=runtime.scenario.radio.subcarrier_spacing_hz,
    )
    return DynamicLinkObservation(
        cell.id, ue.id, geometry, state.los, path_loss, beam, blockage, budget
    )


def _explicit_state(
    scenario: NormalizedScenario, cell_configuration_id: str, ue: RadioUe
) -> PropagationState | None:
    if scenario.models.los_state != "explicit":
        return None
    states = scenario.topology.ue_groups[ue.group_id].explicit_link_states
    if states is None or cell_configuration_id not in states:
        raise InvariantViolation(
            "normalized explicit LOS state is missing",
            {"cell_id": cell_configuration_id, "ue_id": ue.id, "requirement": "PROP-006"},
        )
    return cast(PropagationState, states[cell_configuration_id][ue.ordinal])


def _candidate(runtime: _Runtime, ue_id: str) -> SchedulingCandidate:
    capacity = runtime.full_capacity_by_ue[ue_id]
    sinr = runtime.sinr_by_ue[ue_id]
    return SchedulingCandidate(
        ue_id=ue_id,
        queue_payload_bits=_queued_bits(runtime, ue_id),
        achievable_payload_bits=capacity.capacity_bits_per_interval,
        achievable_rate_bps=capacity.capacity_bit_rate_bps,
        sinr_db=float(sinr.sinr_db),
    )


def _service_plan(
    runtime: _Runtime,
    start_tick: int,
    completion_tick: int,
    ue_id: str,
    allocated_prbs: int,
) -> _UeServicePlan:
    links = runtime.links_by_ue[ue_id]
    serving_id = runtime.handover[ue_id].serving_cell_id
    serving = next(item.link_budget for item in links if item.cell_id == serving_id)
    ue = next(item for item in runtime.topology.ues if item.id == ue_id)
    sinr = calculate_activity_coupled_sinr(
        serving,
        tuple(item.link_budget for item in links),
        allocated_prbs=allocated_prbs,
        available_prbs=runtime.scenario.radio.prb_count,
        previous_active_prbs=runtime.previous_active_prbs,
        receiver_noise_figure_db=ue.receiver_noise_figure_db,
    )
    capacity = evaluate_capacity(
        runtime.scenario.radio, sinr_db=sinr.sinr_db, allocated_prbs=allocated_prbs
    )
    by_bearer = _oldest_packet_first_capacity(runtime, ue_id, capacity.capacity_bits_per_interval)
    reservations = tuple(
        runtime.queues[bearer_id].reserve_service(
            start_tick=start_tick,
            completion_tick=completion_tick,
            capacity_bits=bits,
        )
        for bearer_id, bits in by_bearer
        if bits > 0
    )
    return _UeServicePlan(ue_id, allocated_prbs, sinr, capacity, reservations)


def _oldest_packet_first_capacity(
    runtime: _Runtime, ue_id: str, capacity_bits: int
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
    result: dict[BearerId, int] = defaultdict(int)
    for _, _, _, bearer_id, bits in candidates:
        if remaining == 0:
            break
        selected = min(remaining, bits)
        result[bearer_id] += selected
        remaining -= selected
    return tuple(sorted(result.items()))


def _queued_bits(runtime: _Runtime, ue_id: str) -> int:
    return sum(runtime.queues[key].queued_payload_bits for key in runtime.bearers_by_ue[ue_id])


def _is_available(runtime: _Runtime, ue_id: str, tick: int) -> bool:
    return (
        not runtime.availability[ue_id].outage
        and tick >= runtime.handover[ue_id].interruption_until_tick
    )


def _build_dynamic_kpis(runtime: _Runtime, run_id: str) -> KpiReport:
    records: list[MetricRecord] = []
    start = runtime.scenario.simulation.measurement_start_ns
    end = runtime.scenario.simulation.measurement_end_ns
    measured_frames = [frame for frame in runtime.frames if start <= frame.tick < end]
    frame_count = len(measured_frames)
    for ue in runtime.topology.ues:
        states = [
            next(item for item in frame.ue_states if item.ue_id == ue.id)
            for frame in measured_frames
        ]
        handovers = [
            item
            for item in runtime.handover_transitions
            if item.ue_id == ue.id and item.kind == "handover_executed" and start <= item.tick < end
        ]
        availability = [
            item
            for item in runtime.availability_transitions
            if item.ue_id == ue.id and start <= item.tick < end
        ]
        ping_pongs = sum(item.ping_pong for item in handovers)
        values: tuple[tuple[str, str, int | float | None, int, str | None], ...] = (
            ("handover_count", "count", len(handovers), len(handovers), None),
            ("association_change_count", "count", len(handovers), len(handovers), None),
            ("ping_pong_count", "count", ping_pongs, len(handovers), None),
            (
                "ping_pong_ratio",
                "ratio",
                None if not handovers else ping_pongs / len(handovers),
                len(handovers),
                "zero_denominator" if not handovers else None,
            ),
            (
                "outage_transition_count",
                "count",
                sum(item.kind == "outage_entered" for item in availability),
                len(availability),
                None,
            ),
            (
                "recovery_transition_count",
                "count",
                sum(item.kind == "outage_recovered" for item in availability),
                len(availability),
                None,
            ),
            (
                "handover_interruption_fraction",
                "ratio",
                sum(int(item.handover_interruption) for item in states) / frame_count,
                frame_count,
                None,
            ),
            (
                "availability_outage_fraction",
                "ratio",
                sum(int(item.outage) for item in states) / frame_count,
                frame_count,
                None,
            ),
            (
                "scheduling_availability_ratio",
                "ratio",
                sum(int(item.available_for_scheduling) for item in states) / frame_count,
                frame_count,
                None,
            ),
            (
                "mean_serving_sinr",
                "dB",
                sum(item.sinr.sinr_db for item in states) / frame_count,
                frame_count,
                None,
            ),
        )
        for name, unit, value, samples, null_reason in values:
            records.append(
                MetricRecord(
                    name=name,
                    definition_version=DYNAMIC_KPI_DEFINITION_VERSION,
                    unit=unit,
                    aggregation_level="ue",
                    aggregation_id=ue.id,
                    population_filter="UE dynamic-radio samples in measurement window",
                    interval_start_tick=start,
                    interval_end_tick=end,
                    sample_count=samples,
                    run_id=run_id,
                    value=value,
                    null_reason=cast(Literal["zero_denominator"] | None, null_reason),
                )
            )
    ue_records = tuple(records)
    for name in (
        "handover_count",
        "association_change_count",
        "ping_pong_count",
        "outage_transition_count",
        "recovery_transition_count",
    ):
        selected = [item for item in ue_records if item.name == name]
        records.append(
            MetricRecord(
                name=name,
                definition_version=DYNAMIC_KPI_DEFINITION_VERSION,
                unit="count",
                aggregation_level="system",
                aggregation_id="system",
                population_filter="all configured UEs in measurement window",
                interval_start_tick=start,
                interval_end_tick=end,
                sample_count=sum(item.sample_count for item in selected),
                run_id=run_id,
                value=sum(int(item.value or 0) for item in selected),
            )
        )
    system_states = [state for frame in measured_frames for state in frame.ue_states]
    system_fractions = (
        (
            "handover_interruption_fraction",
            sum(int(state.handover_interruption) for state in system_states),
        ),
        (
            "availability_outage_fraction",
            sum(int(state.outage) for state in system_states),
        ),
        (
            "scheduling_availability_ratio",
            sum(int(state.available_for_scheduling) for state in system_states),
        ),
    )
    for name, numerator in system_fractions:
        records.append(
            MetricRecord(
                name=name,
                definition_version=DYNAMIC_KPI_DEFINITION_VERSION,
                unit="ratio",
                aggregation_level="system",
                aggregation_id="system",
                population_filter="all UE-slot samples in measurement window",
                interval_start_tick=start,
                interval_end_tick=end,
                sample_count=len(system_states),
                run_id=run_id,
                value=numerator / len(system_states),
            )
        )
    system_handovers = sum(
        int(item.value or 0) for item in ue_records if item.name == "handover_count"
    )
    system_ping_pongs = sum(
        int(item.value or 0) for item in ue_records if item.name == "ping_pong_count"
    )
    records.append(
        MetricRecord(
            name="ping_pong_ratio",
            definition_version=DYNAMIC_KPI_DEFINITION_VERSION,
            unit="ratio",
            aggregation_level="system",
            aggregation_id="system",
            population_filter="all handovers in measurement window",
            interval_start_tick=start,
            interval_end_tick=end,
            sample_count=system_handovers,
            run_id=run_id,
            value=None if system_handovers == 0 else system_ping_pongs / system_handovers,
            null_reason="zero_denominator" if system_handovers == 0 else None,
        )
    )
    return KpiReport(DYNAMIC_KPI_DEFINITION_VERSION, tuple(records))


def _validate_slot_boundaries(scenario: NormalizedScenario) -> None:
    slot = scenario.radio.slot_duration_ns
    boundaries = (
        scenario.simulation.measurement_start_ns,
        scenario.simulation.measurement_end_ns,
        scenario.simulation.stop_ns,
    )
    if any(item % slot for item in boundaries):
        raise InvariantViolation(
            "dynamic simulation boundaries must align to complete NR slots",
            {"slot_duration_ns": slot, "requirement": "TIME-002"},
        )


def _combine_rng_streams(*groups: tuple[RngStreamRecord, ...]) -> tuple[RngStreamRecord, ...]:
    combined = tuple(item for group in groups for item in group)
    paths = tuple(item.semantic_path for item in combined)
    if len(paths) != len(set(paths)):
        raise InvariantViolation("dynamic run RNG manifests contain a duplicate semantic path")
    return tuple(sorted(combined, key=lambda item: item.semantic_path))


def _require_payload(event: ScheduledEvent, expected: type[PayloadT]) -> PayloadT:
    if not isinstance(event.payload, expected):
        raise InvariantViolation(
            "kernel event payload does not match its registered handler",
            {"expected": expected.__name__, "received": type(event.payload).__name__},
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


def _semantic_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(
        canonicalize_floats(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
