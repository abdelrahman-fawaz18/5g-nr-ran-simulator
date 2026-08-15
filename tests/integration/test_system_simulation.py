from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from nr_ran_sim.config.models import ScenarioConfig
from nr_ran_sim.config.normalize import normalize_scenario
from nr_ran_sim.errors import ArtifactError, InvariantViolation
from nr_ran_sim.experiments.simulation import SimulationResult, run_system_simulation

MASTER_SEED = "0x33333333333333333333333333333333"
REVISION = "a" * 40


def _scenario(data: dict[str, Any]):  # type: ignore[no-untyped-def]
    return normalize_scenario(ScenarioConfig.model_validate(data))


def _run(data: dict[str, Any]) -> SimulationResult:
    return run_system_simulation(
        _scenario(data),
        master_seed=MASTER_SEED,
        replication_id=2,
        code_revision=REVISION,
        working_tree_dirty=False,
    )


def _metric(
    result: SimulationResult,
    name: str,
    level: str,
    aggregate_id: str,
) -> float | int | None:
    return next(
        item.value
        for item in result.kpis.records
        if item.name == name
        and item.aggregation_level == level
        and item.aggregation_id == aggregate_id
    )


def test_integrated_simulation_is_replay_stable_and_conserves_prbs_bits_and_packets(
    scheduler_scenario_data: dict[str, Any],
) -> None:
    first = _run(scheduler_scenario_data)
    replay = _run(scheduler_scenario_data)

    assert first.semantic_sha256 == replay.semantic_sha256
    assert first.semantic_dict() == replay.semantic_dict()
    assert first.scheduler_policy_id == "proportional-fair-v1"
    assert len(first.intervals) == 12
    assert all(
        sum(outcome.allocated_prbs for outcome in interval.outcomes) <= interval.available_prbs
        for interval in first.intervals
    )
    assert all(
        outcome.served_payload_bits
        <= outcome.reserved_payload_bits
        <= outcome.scheduled_capacity_bits
        for interval in first.intervals
        for outcome in interval.outcomes
    )
    assert all(ledger.active_packets == 0 for _, ledger in first.queue_ledgers)
    completed = [
        packet
        for _, snapshots in first.packet_snapshots
        for packet in snapshots
        if packet.completion_tick is not None
    ]
    assert completed
    assert all(packet.first_service_tick is not None for packet in completed)
    assert all(
        packet.completion_tick - packet.first_service_tick >= 500_000
        for packet in completed
        if packet.completion_tick is not None and packet.first_service_tick is not None
    )
    assert all(record.run_id == str(first.identity.id) for record in first.kpis.records)
    assert all(record.definition_version == "1.0" for record in first.kpis.records)


def test_policy_comparison_reuses_exogenous_streams_and_exposes_expected_fairness_tradeoff(
    scheduler_scenario_data: dict[str, Any],
) -> None:
    pf_data = copy.deepcopy(scheduler_scenario_data)
    rr_data = copy.deepcopy(scheduler_scenario_data)
    rr_data["scheduler"] = {"policy": "round-robin", "parameters": {}}
    max_data = copy.deepcopy(scheduler_scenario_data)
    max_data["scheduler"] = {"policy": "max-ci", "parameters": {}}

    pf = _run(pf_data)
    rr = _run(rr_data)
    max_ci = _run(max_data)

    assert pf.exogenous_configuration_sha256 == rr.exogenous_configuration_sha256
    assert rr.exogenous_configuration_sha256 == max_ci.exogenous_configuration_sha256
    assert (
        pf.configuration_manifest.configuration_sha256
        != rr.configuration_manifest.configuration_sha256
    )
    assert (
        pf.radio_snapshot.topology == rr.radio_snapshot.topology == max_ci.radio_snapshot.topology
    )
    assert pf.radio_snapshot.links == rr.radio_snapshot.links == max_ci.radio_snapshot.links
    packet_inputs = lambda result: [  # noqa: E731
        (packet.packet.id, packet.packet.arrival_tick, packet.packet.payload_bits)
        for _, snapshots in result.packet_snapshots
        for packet in snapshots
    ]
    assert packet_inputs(pf) == packet_inputs(rr) == packet_inputs(max_ci)

    rr_fairness = _metric(rr, "jain_fairness", "system", "system")
    max_fairness = _metric(max_ci, "jain_fairness", "system", "system")
    assert isinstance(rr_fairness, float)
    assert isinstance(max_fairness, float)
    assert rr_fairness > max_fairness
    assert {item.scheduler_policy_id for item in (pf, rr, max_ci)} == {
        "proportional-fair-v1",
        "round-robin-v1",
        "max-ci-v1",
    }


def test_kpi_records_distinguish_rates_delays_outcomes_fairness_and_resources(
    scheduler_scenario_data: dict[str, Any],
) -> None:
    result = _run(scheduler_scenario_data)
    names = {record.name for record in result.kpis.records}
    assert {
        "offered_load_bps",
        "scheduled_capacity_bps",
        "served_throughput_bps",
        "cohort_goodput_bps",
        "queueing_delay_p95_ns",
        "service_span_p95_ns",
        "system_delay_p95_ns",
        "jitter_mean_absolute_successive_delay_ns",
        "delivery_ratio",
        "deadline_success_ratio",
        "overflow_drop_ratio",
        "censor_ratio",
        "jain_fairness",
        "payload_spectral_efficiency_bit_per_s_per_hz",
        "prb_utilization",
        "wasted_allocation_ratio",
        "outage_fraction",
    } <= names
    for name in ("delivery_ratio", "prb_utilization", "wasted_allocation_ratio"):
        value = _metric(result, name, "system", "system")
        assert value is None or 0 <= value <= 1
    deadline = next(
        record
        for record in result.kpis.records
        if record.name == "deadline_success_ratio" and record.aggregation_level == "system"
    )
    assert deadline.value is None
    assert deadline.null_reason == "zero_denominator"
    assert {record.aggregation_level for record in result.kpis.records} >= {
        "bearer",
        "ue",
        "application",
        "cell",
        "system",
    }


def test_paired_stochastic_policy_runs_keep_radio_and_traffic_draws_identical(
    scheduler_scenario_data: dict[str, Any],
) -> None:
    pf_data = copy.deepcopy(scheduler_scenario_data)
    group = pf_data["topology"]["ue_groups"]["users"]
    group.pop("explicit_link_states")
    group["placement"] = {
        "mode": "uniform_rectangle",
        "x_min": {"value": 100, "unit": "m"},
        "x_max": {"value": 400, "unit": "m"},
        "y_min": {"value": 0, "unit": "m"},
        "y_max": {"value": 100, "unit": "m"},
        "height": {"value": 1.5, "unit": "m"},
        "minimum_2d_distance": {"value": 10, "unit": "m"},
        "attempt_budget": 1000,
    }
    pf_data["models"].update({"los_state": "probability_static", "shadowing": "independent_static"})
    pf_data["traffic_profiles"]["broadband"]["source"] = {
        "type": "poisson",
        "mean_interarrival": {"value": 0.5, "unit": "ms"},
    }
    rr_data = copy.deepcopy(pf_data)
    rr_data["scenario_id"] = "renamed-policy-comparison"
    rr_data["description"] = "Labels and scheduler do not perturb exogenous draws"
    rr_data["scheduler"] = {"policy": "round-robin", "parameters": {}}

    pf = _run(pf_data)
    rr = _run(rr_data)

    assert pf.exogenous_configuration_sha256 == rr.exogenous_configuration_sha256
    assert pf.radio_snapshot.topology == rr.radio_snapshot.topology
    assert pf.radio_snapshot.links == rr.radio_snapshot.links
    assert [(record.semantic_path, record.fingerprint) for record in pf.rng_streams] == [
        (record.semantic_path, record.fingerprint) for record in rr.rng_streams
    ]
    assert [
        (snapshot.packet.arrival_tick, snapshot.packet.payload_bits)
        for _, snapshots in pf.packet_snapshots
        for snapshot in snapshots
    ] == [
        (snapshot.packet.arrival_tick, snapshot.packet.payload_bits)
        for _, snapshots in rr.packet_snapshots
        for snapshot in snapshots
    ]


def test_simulation_artifact_is_atomic_collision_safe_and_metadata_is_not_semantic(
    tmp_path: Path,
    scheduler_scenario_data: dict[str, Any],
) -> None:
    clean = _run(scheduler_scenario_data)
    dirty = run_system_simulation(
        _scenario(scheduler_scenario_data),
        master_seed=MASTER_SEED,
        replication_id=2,
        code_revision=REVISION,
        working_tree_dirty=True,
    )
    assert clean.semantic_sha256 == dirty.semantic_sha256
    assert clean.metadata.working_tree_dirty is False
    assert dirty.metadata.working_tree_dirty is True
    target = tmp_path / "nested" / "simulation.json"
    clean.write(target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["semantic_sha256"] == clean.semantic_sha256
    with pytest.raises(ArtifactError, match="already exists"):
        clean.write(target)
    clean.write(target, force=True)


def test_integrated_simulation_rejects_partial_slot_windows(
    scheduler_scenario_data: dict[str, Any],
) -> None:
    scheduler_scenario_data["simulation"]["warmup"] = {"value": 1.1, "unit": "ms"}
    with pytest.raises(InvariantViolation, match="align"):
        _run(scheduler_scenario_data)
