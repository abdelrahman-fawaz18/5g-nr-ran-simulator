from __future__ import annotations

from typing import Any

import pytest

from nr_ran_sim.config.manifest import build_manifest
from nr_ran_sim.config.models import ScenarioConfig
from nr_ran_sim.config.normalize import NormalizedScenario, normalize_scenario
from nr_ran_sim.domain import BearerId, TerminalCause
from nr_ran_sim.errors import RunExecutionError
from nr_ran_sim.traffic import ServiceGrant, run_traffic_mechanics

MASTER = "0x0123456789abcdeffedcba9876543210"
REVISION = "b" * 40


def _small_scenario(data: dict[str, Any], *, deadline: bool = True) -> NormalizedScenario:
    data["simulation"] = {
        "warmup": {"value": 0, "unit": "ms"},
        "measurement": {"value": 30, "unit": "ms"},
        "drain": {"value": 20, "unit": "ms"},
    }
    data["topology"]["ue_groups"]["users"]["count"] = 1
    profile = data["traffic_profiles"]["broadband"]
    profile["source"] = {
        "type": "periodic",
        "interval": {"value": 10, "unit": "ms"},
        "initial_offset": {"value": 0, "unit": "ms"},
    }
    profile["packet_size"] = {
        "type": "constant",
        "payload": {"value": 100, "unit": "bit"},
    }
    profile["queue"] = {
        "max_packets": 2,
        "max_payload": {"value": 200, "unit": "bit"},
    }
    profile["deadline"] = {"value": 15, "unit": "ms"} if deadline else None
    return normalize_scenario(ScenarioConfig.model_validate(data))


def test_radio_independent_mechanics_replay_and_deadline_boundary(
    scenario_data: dict[str, Any],
) -> None:
    scenario = _small_scenario(scenario_data)
    configuration_sha = build_manifest(scenario).configuration_sha256
    bearer_id = BearerId("bearer/users/000000/broadband")
    grants = (
        ServiceGrant(bearer_id=bearer_id, tick=15_000_000, capacity_bits=100),
        ServiceGrant(bearer_id=bearer_id, tick=25_000_000, capacity_bits=50),
    )

    first = run_traffic_mechanics(
        scenario,
        configuration_sha256=configuration_sha,
        master_seed=MASTER,
        replication_id=0,
        code_revision=REVISION,
        working_tree_dirty=False,
        service_grants=grants,
    )
    replay = run_traffic_mechanics(
        scenario,
        configuration_sha256=configuration_sha,
        master_seed=MASTER,
        replication_id=0,
        code_revision=REVISION,
        working_tree_dirty=True,
        service_grants=tuple(reversed(grants)),
    )

    assert first.to_semantic_json() == replay.to_semantic_json()
    assert first.semantic_sha256 == replay.semantic_sha256
    assert first.metadata.working_tree_dirty is False
    assert replay.metadata.working_tree_dirty is True
    tick_15 = [event for event in first.trace.events if event.tick == 15_000_000]
    assert [(event.phase, event.kind, event.outcome) for event in tick_15] == [
        (10, "service_completion", "service_applied"),
        (20, "packet_deadline", "already_terminal"),
    ]
    snapshots = first.packet_snapshots[0][1]
    assert [snapshot.terminal_cause for snapshot in snapshots] == [
        TerminalCause.COMPLETED,
        TerminalCause.DEADLINE_EXPIRED,
        TerminalCause.DEADLINE_EXPIRED,
    ]
    ledger = first.queue_ledgers[0][1]
    assert ledger.completed_packets == 1
    assert ledger.terminal_packets == 2
    assert ledger.offered_bits == 300


def test_measurement_sources_stop_before_drain_and_unfinished_packets_are_censored(
    scenario_data: dict[str, Any],
) -> None:
    scenario = _small_scenario(scenario_data, deadline=False)
    result = run_traffic_mechanics(
        scenario,
        configuration_sha256=build_manifest(scenario).configuration_sha256,
        master_seed=MASTER,
        replication_id=1,
        code_revision=REVISION,
        working_tree_dirty=False,
    )

    snapshots = result.packet_snapshots[0][1]
    assert [snapshot.packet.arrival_tick for snapshot in snapshots] == [
        0,
        10_000_000,
        20_000_000,
    ]
    assert all(
        snapshot.terminal_cause is TerminalCause.CENSORED_AT_STOP for snapshot in snapshots[:2]
    )
    assert snapshots[2].terminal_cause is TerminalCause.OVERFLOW_DROP
    assert result.trace.events[-1].tick == scenario.simulation.stop_ns
    assert result.trace.events[-1].kind == "censor_at_stop"


def test_poisson_mechanics_records_owned_rng_and_replays(
    scenario_data: dict[str, Any],
) -> None:
    scenario_data["simulation"] = {
        "warmup": {"value": 0, "unit": "ns"},
        "measurement": {"value": 1000, "unit": "ns"},
        "drain": {"value": 0, "unit": "ns"},
    }
    scenario_data["topology"]["ue_groups"]["users"]["count"] = 1
    profile = scenario_data["traffic_profiles"]["broadband"]
    profile["source"] = {
        "type": "poisson",
        "mean_interarrival": {"value": 100, "unit": "ns"},
    }
    profile["packet_size"] = {
        "type": "discrete_uniform",
        "minimum_payload": {"value": 80, "unit": "bit"},
        "maximum_payload": {"value": 120, "unit": "bit"},
    }
    profile["queue"] = {"max_packets": 100}
    profile["deadline"] = None
    scenario = normalize_scenario(ScenarioConfig.model_validate(scenario_data))
    configuration_sha = build_manifest(scenario).configuration_sha256

    def execute() -> tuple[str, tuple[str, ...]]:
        result = run_traffic_mechanics(
            scenario,
            configuration_sha256=configuration_sha,
            master_seed=MASTER,
            replication_id=9,
            code_revision=REVISION,
            working_tree_dirty=False,
        )
        return result.semantic_sha256, tuple(record.semantic_path for record in result.rng_streams)

    first = execute()
    assert first == execute()
    assert first[1] == (
        "traffic/bearer/users/000000/broadband/interarrival",
        "traffic/bearer/users/000000/broadband/packet-size",
    )


def test_service_grants_must_reference_known_bearers_and_slot_boundaries(
    scenario_data: dict[str, Any],
) -> None:
    scenario = _small_scenario(scenario_data)
    configuration_sha = build_manifest(scenario).configuration_sha256
    common = {
        "configuration_sha256": configuration_sha,
        "master_seed": MASTER,
        "replication_id": 0,
        "code_revision": REVISION,
        "working_tree_dirty": False,
    }
    with pytest.raises(RunExecutionError, match="slot boundary"):
        run_traffic_mechanics(
            scenario,
            **common,
            service_grants=(
                ServiceGrant(
                    bearer_id=BearerId("bearer/users/000000/broadband"),
                    tick=1,
                    capacity_bits=10,
                ),
            ),
        )
    with pytest.raises(RunExecutionError, match="unknown bearer"):
        run_traffic_mechanics(
            scenario,
            **common,
            service_grants=(
                ServiceGrant(
                    bearer_id=BearerId("bearer/missing"),
                    tick=0,
                    capacity_bits=10,
                ),
            ),
        )
