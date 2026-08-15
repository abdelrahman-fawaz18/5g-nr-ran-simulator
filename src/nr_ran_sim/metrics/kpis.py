"""Pure KPI reducers implementing the frozen Tier A KPI Contract 1.0."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import pairwise

from nr_ran_sim.config.normalize import NormalizedScenario
from nr_ran_sim.domain.entities import EntityRegistry
from nr_ran_sim.domain.packets import PacketCohort, PacketSnapshot, TerminalCause
from nr_ran_sim.metrics.records import KpiReport, MetricRecord, SchedulingIntervalRecord

KPI_DEFINITION_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class _Group:
    level: str
    id: str
    bearer_ids: frozenset[str]
    ue_ids: frozenset[str]


def build_kpi_report(
    scenario: NormalizedScenario,
    entities: EntityRegistry,
    *,
    run_id: str,
    serving_cells: dict[str, str],
    packet_snapshots: tuple[tuple[str, tuple[PacketSnapshot, ...]], ...],
    intervals: tuple[SchedulingIntervalRecord, ...],
) -> KpiReport:
    """Reduce immutable packet and scheduling records into definition-versioned KPIs."""

    start = scenario.simulation.measurement_start_ns
    end = scenario.simulation.measurement_end_ns
    duration_ns = end - start
    snapshot_by_bearer = dict(packet_snapshots)
    groups = _build_groups(scenario, entities, serving_cells)
    records: list[MetricRecord] = []
    ue_by_bearer = {str(bearer.id): str(bearer.ue_id) for bearer in entities.bearers}

    for group in groups:
        packets = tuple(
            snapshot
            for bearer_id in sorted(group.bearer_ids)
            for snapshot in snapshot_by_bearer.get(bearer_id, ())
            if snapshot.packet.cohort is PacketCohort.MEASUREMENT
        )
        offered_bits = sum(snapshot.packet.payload_bits for snapshot in packets)
        completed = tuple(
            snapshot
            for snapshot in packets
            if snapshot.terminal_cause is TerminalCause.COMPLETED
            and snapshot.completion_tick is not None
            and snapshot.completion_tick <= scenario.simulation.stop_ns
        )
        served_bits = _served_bits(intervals, group.bearer_ids, start, end)
        records.extend(
            (
                _rate_record(
                    "offered_load_bps",
                    group,
                    run_id,
                    start,
                    end,
                    offered_bits,
                    duration_ns,
                    len(packets),
                    "measurement-cohort arrivals",
                ),
                _rate_record(
                    "served_throughput_bps",
                    group,
                    run_id,
                    start,
                    end,
                    served_bits,
                    duration_ns,
                    len(packets),
                    "queue payload removed by completions in measurement window",
                ),
                _rate_record(
                    "cohort_goodput_bps",
                    group,
                    run_id,
                    start,
                    end,
                    sum(snapshot.packet.payload_bits for snapshot in completed),
                    duration_ns,
                    len(completed),
                    "measurement-cohort packets completed by drain end",
                ),
            )
        )
        records.extend(_delay_records(group, run_id, start, end, packets, completed))
        records.extend(_outcome_records(group, run_id, start, end, packets, completed))

    bearer_groups = tuple(group for group in groups if group.level == "bearer")
    for group in bearer_groups:
        packets = tuple(
            snapshot
            for snapshot in snapshot_by_bearer.get(next(iter(group.bearer_ids)), ())
            if snapshot.packet.cohort is PacketCohort.MEASUREMENT
            and snapshot.terminal_cause is TerminalCause.COMPLETED
            and snapshot.completion_tick is not None
        )
        packets = tuple(
            sorted(packets, key=lambda item: (item.completion_tick or 0, str(item.packet.id)))
        )
        delays = [
            snapshot.completion_tick - snapshot.packet.arrival_tick
            for snapshot in packets
            if snapshot.completion_tick is not None
        ]
        records.append(_jitter_record(group, run_id, start, end, delays))

    records.extend(
        _scheduler_resource_records(
            scenario,
            entities,
            run_id,
            serving_cells,
            intervals,
            snapshot_by_bearer,
            ue_by_bearer,
        )
    )
    return KpiReport(
        definition_version=KPI_DEFINITION_VERSION,
        records=tuple(
            sorted(
                records,
                key=lambda record: (
                    record.name,
                    record.aggregation_level,
                    record.aggregation_id,
                ),
            )
        ),
    )


def _build_groups(
    scenario: NormalizedScenario,
    entities: EntityRegistry,
    serving_cells: dict[str, str],
) -> tuple[_Group, ...]:
    bearer_to_ue = {str(bearer.id): str(bearer.ue_id) for bearer in entities.bearers}
    bearer_to_profile = {str(bearer.id): bearer.traffic_profile_id for bearer in entities.bearers}
    all_bearers = frozenset(bearer_to_ue)
    all_ues = frozenset(str(ue.id) for ue in entities.ues)
    groups: list[_Group] = [_Group("system", "system", all_bearers, all_ues)]
    for cell in entities.cells:
        cell_id = str(cell.id)
        ues = frozenset(ue_id for ue_id, serving in serving_cells.items() if serving == cell_id)
        bearers = frozenset(bearer_id for bearer_id, ue_id in bearer_to_ue.items() if ue_id in ues)
        groups.append(_Group("cell", cell_id, bearers, ues))
    for profile_id in sorted(scenario.traffic_profiles):
        bearers = frozenset(
            bearer_id
            for bearer_id, configured_profile in bearer_to_profile.items()
            if configured_profile == profile_id
        )
        groups.append(
            _Group(
                "application",
                profile_id,
                bearers,
                frozenset(bearer_to_ue[bearer_id] for bearer_id in bearers),
            )
        )
    for ue in entities.ues:
        ue_id = str(ue.id)
        bearers = frozenset(
            bearer_id for bearer_id, owner in bearer_to_ue.items() if owner == ue_id
        )
        groups.append(_Group("ue", ue_id, bearers, frozenset({ue_id})))
    for bearer in entities.bearers:
        bearer_id = str(bearer.id)
        groups.append(
            _Group("bearer", bearer_id, frozenset({bearer_id}), frozenset({str(bearer.ue_id)}))
        )
    return tuple(groups)


def _delay_records(
    group: _Group,
    run_id: str,
    start: int,
    end: int,
    packets: tuple[PacketSnapshot, ...],
    completed: tuple[PacketSnapshot, ...],
) -> tuple[MetricRecord, ...]:
    censored = sum(
        snapshot.terminal_cause is TerminalCause.CENSORED_AT_STOP for snapshot in packets
    )
    extractors: tuple[tuple[str, Callable[[PacketSnapshot], int]], ...] = (
        (
            "queueing_delay",
            lambda item: _required(item.first_service_tick) - item.packet.arrival_tick,
        ),
        (
            "service_span",
            lambda item: _required(item.completion_tick) - _required(item.first_service_tick),
        ),
        ("system_delay", lambda item: _required(item.completion_tick) - item.packet.arrival_tick),
    )
    records: list[MetricRecord] = []
    for prefix, extractor in extractors:
        values = sorted(float(extractor(snapshot)) for snapshot in completed)
        for suffix, probability in (("median", 0.5), ("p95", 0.95), ("p99", 0.99)):
            value = None if not values else _type7_quantile(values, probability)
            records.append(
                _record(
                    f"{prefix}_{suffix}_ns",
                    "ns",
                    group,
                    run_id,
                    start,
                    end,
                    len(values),
                    value,
                    "completed measurement-cohort packets",
                    null_reason="insufficient_samples" if value is None else None,
                    details={
                        "censor_count": censored,
                        "percentile_method": "Hyndman-Fan type 7",
                    },
                )
            )
    return tuple(records)


def _outcome_records(
    group: _Group,
    run_id: str,
    start: int,
    end: int,
    packets: tuple[PacketSnapshot, ...],
    completed: tuple[PacketSnapshot, ...],
) -> tuple[MetricRecord, ...]:
    deadline_packets = tuple(
        snapshot for snapshot in packets if snapshot.packet.deadline_tick is not None
    )
    deadline_successes = sum(
        snapshot.terminal_cause is TerminalCause.COMPLETED
        and snapshot.completion_tick is not None
        and snapshot.packet.deadline_tick is not None
        and snapshot.completion_tick <= snapshot.packet.deadline_tick
        for snapshot in deadline_packets
    )
    definitions = (
        ("delivery_ratio", len(completed), len(packets), "all measurement-cohort arrivals"),
        (
            "deadline_success_ratio",
            deadline_successes,
            len(deadline_packets),
            "deadline-bearing measurement-cohort arrivals",
        ),
        (
            "overflow_drop_ratio",
            sum(snapshot.terminal_cause is TerminalCause.OVERFLOW_DROP for snapshot in packets),
            len(packets),
            "all measurement-cohort arrivals",
        ),
        (
            "deadline_drop_ratio",
            sum(
                snapshot.terminal_cause is TerminalCause.DEADLINE_EXPIRED
                for snapshot in deadline_packets
            ),
            len(deadline_packets),
            "deadline-bearing measurement-cohort arrivals",
        ),
        (
            "censor_ratio",
            sum(snapshot.terminal_cause is TerminalCause.CENSORED_AT_STOP for snapshot in packets),
            len(packets),
            "all measurement-cohort arrivals",
        ),
    )
    return tuple(
        _ratio_record(name, group, run_id, start, end, numerator, denominator, population)
        for name, numerator, denominator, population in definitions
    )


def _scheduler_resource_records(
    scenario: NormalizedScenario,
    entities: EntityRegistry,
    run_id: str,
    serving_cells: dict[str, str],
    intervals: tuple[SchedulingIntervalRecord, ...],
    snapshots: dict[str, tuple[PacketSnapshot, ...]],
    ue_by_bearer: dict[str, str],
) -> tuple[MetricRecord, ...]:
    start = scenario.simulation.measurement_start_ns
    end = scenario.simulation.measurement_end_ns
    duration_ns = end - start
    measured = tuple(item for item in intervals if start <= item.start_tick < end)
    records: list[MetricRecord] = []
    cell_ids = tuple(str(cell.id) for cell in entities.cells)
    for level, aggregate_id, selected_cells in (
        *(("cell", cell_id, frozenset({cell_id})) for cell_id in cell_ids),
        ("system", "system", frozenset(cell_ids)),
    ):
        group_intervals = tuple(item for item in measured if item.cell_id in selected_cells)
        completed_intervals = tuple(
            item
            for item in intervals
            if item.cell_id in selected_cells and start <= item.completion_tick < end
        )
        outcomes = tuple(outcome for item in group_intervals for outcome in item.outcomes)
        available = sum(item.available_prbs for item in group_intervals)
        allocated = sum(outcome.allocated_prbs for outcome in outcomes)
        wasted = sum(
            outcome.allocated_prbs for outcome in outcomes if outcome.served_payload_bits == 0
        )
        eligible_count = sum(len(item.eligible_ue_ids) for item in group_intervals)
        outage_count = sum(len(item.outage_ue_ids) for item in group_intervals)
        scheduled_bits = sum(outcome.scheduled_capacity_bits for outcome in outcomes)
        served_bits = sum(
            outcome.served_payload_bits for item in completed_intervals for outcome in item.outcomes
        )
        synthetic = _Group(level, aggregate_id, frozenset(), frozenset())
        records.extend(
            (
                _rate_record(
                    "scheduled_capacity_bps",
                    synthetic,
                    run_id,
                    start,
                    end,
                    scheduled_bits,
                    duration_ns,
                    len(outcomes),
                    "capacity committed by scheduler in measurement window",
                ),
                _ratio_record(
                    "prb_utilization",
                    synthetic,
                    run_id,
                    start,
                    end,
                    allocated,
                    available,
                    "allocated PRB-slots / available PRB-slots",
                ),
                _ratio_record(
                    "wasted_allocation_ratio",
                    synthetic,
                    run_id,
                    start,
                    end,
                    wasted,
                    allocated,
                    "allocated PRB-slots carrying zero queue payload",
                ),
                _ratio_record(
                    "outage_fraction",
                    synthetic,
                    run_id,
                    start,
                    end,
                    outage_count,
                    eligible_count,
                    "eligible scheduling observations",
                ),
                _record(
                    "payload_spectral_efficiency_bit_per_s_per_hz",
                    "bit/s/Hz",
                    synthetic,
                    run_id,
                    start,
                    end,
                    len(outcomes),
                    _spectral_efficiency(
                        served_bits,
                        duration_ns,
                        scenario.radio.transmission_bandwidth_hz * len(selected_cells),
                    ),
                    "served payload over actual transmission bandwidth",
                ),
            )
        )

    for ue in entities.ues:
        ue_id = str(ue.id)
        outcomes = tuple(
            outcome for item in measured for outcome in item.outcomes if outcome.ue_id == ue_id
        )
        synthetic = _Group("ue", ue_id, frozenset(), frozenset({ue_id}))
        records.append(
            _rate_record(
                "scheduled_capacity_bps",
                synthetic,
                run_id,
                start,
                end,
                sum(outcome.scheduled_capacity_bits for outcome in outcomes),
                duration_ns,
                len(outcomes),
                "capacity committed to UE by scheduler in measurement window",
            )
        )

    cohort_by_ue: dict[str, list[PacketSnapshot]] = defaultdict(list)
    for bearer_id, bearer_snapshots in snapshots.items():
        ue_id = ue_by_bearer[bearer_id]
        cohort_by_ue[ue_id].extend(
            item for item in bearer_snapshots if item.packet.cohort is PacketCohort.MEASUREMENT
        )
    for level, aggregate_id, ue_ids in (
        *(
            (
                "cell",
                cell_id,
                tuple(sorted(ue for ue, cell in serving_cells.items() if cell == cell_id)),
            )
            for cell_id in cell_ids
        ),
        ("system", "system", tuple(sorted(serving_cells))),
    ):
        active_rates: list[float] = []
        for ue_id in ue_ids:
            packets = cohort_by_ue.get(ue_id, [])
            offered = sum(item.packet.payload_bits for item in packets)
            if offered <= 0:
                continue
            completed_bits = sum(
                item.packet.payload_bits
                for item in packets
                if item.terminal_cause is TerminalCause.COMPLETED
            )
            active_rates.append(completed_bits * 1_000_000_000 / duration_ns)
        synthetic = _Group(level, aggregate_id, frozenset(), frozenset(ue_ids))
        fairness = _jain(active_rates)
        records.append(
            _record(
                "jain_fairness",
                "ratio",
                synthetic,
                run_id,
                start,
                end,
                len(active_rates),
                fairness,
                "active UEs with positive offered load",
                null_reason="zero_denominator" if fairness is None else None,
                details={"active_ue_count": len(active_rates)},
            )
        )
        p5 = None if not active_rates else _type7_quantile(sorted(active_rates), 0.05)
        records.append(
            _record(
                "fifth_percentile_ue_goodput_bps",
                "bit/s",
                synthetic,
                run_id,
                start,
                end,
                len(active_rates),
                p5,
                "active UEs with positive offered load",
                null_reason="insufficient_samples" if p5 is None else None,
                details={"percentile_method": "Hyndman-Fan type 7"},
            )
        )
    return tuple(records)


def _served_bits(
    intervals: tuple[SchedulingIntervalRecord, ...],
    bearer_ids: frozenset[str],
    start: int,
    end: int,
) -> int:
    return sum(
        service.served_bits
        for interval in intervals
        if start <= interval.completion_tick < end
        for outcome in interval.outcomes
        for service in outcome.bearer_services
        if service.bearer_id in bearer_ids
    )


def _rate_record(
    name: str,
    group: _Group,
    run_id: str,
    start: int,
    end: int,
    bits: int,
    duration_ns: int,
    sample_count: int,
    population: str,
) -> MetricRecord:
    value = None if duration_ns == 0 else bits * 1_000_000_000 / duration_ns
    return _record(
        name,
        "bit/s",
        group,
        run_id,
        start,
        end,
        sample_count,
        value,
        population,
        null_reason="zero_denominator" if value is None else None,
        details={"numerator_bits": bits},
    )


def _ratio_record(
    name: str,
    group: _Group,
    run_id: str,
    start: int,
    end: int,
    numerator: int,
    denominator: int,
    population: str,
) -> MetricRecord:
    value = None if denominator == 0 else numerator / denominator
    return _record(
        name,
        "ratio",
        group,
        run_id,
        start,
        end,
        denominator,
        value,
        population,
        null_reason="zero_denominator" if value is None else None,
        details={"numerator": numerator, "denominator": denominator},
    )


def _jitter_record(
    group: _Group,
    run_id: str,
    start: int,
    end: int,
    delays: list[int],
) -> MetricRecord:
    value = None
    if len(delays) >= 2:
        value = sum(abs(current - previous) for previous, current in pairwise(delays)) / (
            len(delays) - 1
        )
    return _record(
        "jitter_mean_absolute_successive_delay_ns",
        "ns",
        group,
        run_id,
        start,
        end,
        len(delays),
        value,
        "completed measurement-cohort packets ordered by completion",
        null_reason="insufficient_samples" if value is None else None,
    )


def _record(
    name: str,
    unit: str,
    group: _Group,
    run_id: str,
    start: int,
    end: int,
    sample_count: int,
    value: int | float | None,
    population: str,
    *,
    null_reason: str | None = None,
    details: dict[str, str | int] | None = None,
) -> MetricRecord:
    return MetricRecord(
        name=name,
        definition_version=KPI_DEFINITION_VERSION,
        unit=unit,
        aggregation_level=group.level,
        aggregation_id=group.id,
        population_filter=population,
        interval_start_tick=start,
        interval_end_tick=end,
        sample_count=sample_count,
        run_id=run_id,
        value=value,
        null_reason=null_reason,  # type: ignore[arg-type]
        details=tuple(sorted((details or {}).items())),
    )


def _type7_quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one sample")
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + fraction * (values[upper] - values[lower])


def _jain(values: Iterable[float]) -> float | None:
    samples = tuple(values)
    denominator = len(samples) * math.fsum(value * value for value in samples)
    if not samples or denominator == 0:
        return None
    numerator = math.fsum(samples) ** 2
    return numerator / denominator


def _spectral_efficiency(bits: int, duration_ns: int, bandwidth_hz: int) -> float | None:
    denominator = duration_ns * bandwidth_hz
    return None if denominator == 0 else bits * 1_000_000_000 / denominator


def _required(value: int | None) -> int:
    if value is None:
        raise ValueError("completed packet is missing a required lifecycle tick")
    return value
