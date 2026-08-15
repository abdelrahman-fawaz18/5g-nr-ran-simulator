from __future__ import annotations

import statistics

import pytest

from nr_ran_sim.domain import BearerId, BearerRecord, PacketCohort, UeId
from nr_ran_sim.errors import InvariantViolation
from nr_ran_sim.experiments import SemanticRngRegistry
from nr_ran_sim.traffic import (
    BoundedUniformInterarrival,
    ConstantPacketSize,
    DiscreteUniformPacketSize,
    PeriodicInterarrival,
    PoissonInterarrival,
    TrafficGenerator,
)

MASTER = "0x0123456789abcdeffedcba9876543210"
BEARER = BearerRecord(
    id=BearerId("bearer/users/000000/test"),
    ue_id=UeId("ue/users/000000"),
    traffic_profile_id="test",
)


def _registry() -> SemanticRngRegistry:
    return SemanticRngRegistry("baseline", MASTER, 3)


def test_periodic_source_and_phase_cohorts_are_exact() -> None:
    generator = TrafficGenerator(
        bearer=BEARER,
        interarrival=PeriodicInterarrival(interval_ns=10, initial_offset_ns=0),
        packet_size=ConstantPacketSize(100),
        deadline_ns=15,
    )

    packets = generator.packets(
        generation_start_tick=0,
        measurement_start_tick=20,
        generation_stop_tick=41,
    )

    assert [packet.arrival_tick for packet in packets] == [0, 10, 20, 30, 40]
    assert [packet.deadline_tick for packet in packets] == [15, 25, 35, 45, 55]
    assert [packet.cohort for packet in packets] == [
        PacketCohort.WARMUP,
        PacketCohort.WARMUP,
        PacketCohort.MEASUREMENT,
        PacketCohort.MEASUREMENT,
        PacketCohort.MEASUREMENT,
    ]
    assert len({packet.id for packet in packets}) == len(packets)


def test_semantic_rng_replay_and_unrelated_stream_perturbation() -> None:
    target_path = "traffic/bearer/users/000000/test/interarrival"
    first_registry = _registry()
    first = first_registry.acquire(target_path, owner="target")
    first_values = tuple(first.exponential(1000.0) for _ in range(20))

    second_registry = _registry()
    unrelated = second_registry.acquire(
        "traffic/bearer/users/999999/other/interarrival", owner="other"
    )
    tuple(unrelated.exponential(50.0) for _ in range(100))
    replay = second_registry.acquire(target_path, owner="target")
    replay_values = tuple(replay.exponential(1000.0) for _ in range(20))

    assert first_values == replay_values
    assert first.record.fingerprint == replay.record.fingerprint
    assert [record.semantic_path for record in second_registry.manifest()] == sorted(
        record.semantic_path for record in second_registry.manifest()
    )


def test_rng_registry_enforces_one_owner_per_path() -> None:
    registry = _registry()
    registry.acquire("traffic/a/interarrival", owner="a")
    with pytest.raises(InvariantViolation, match="already has an owner"):
        registry.acquire("traffic/a/interarrival", owner="b")


def test_poisson_interarrival_statistical_sanity_has_predeclared_tolerance() -> None:
    mean_ns = 1_000_000
    source = PoissonInterarrival(
        mean_ns,
        _registry().acquire("traffic/test/poisson", owner="statistical-test"),
    )
    samples = [source.next_interval_ns() for _ in range(50_000)]

    # For n=50,000 exponential draws, 2% is over four standard errors.
    assert abs(statistics.fmean(samples) - mean_ns) / mean_ns < 0.02
    # Population median is ln(2) * mean; 3% is a conservative fixed acceptance band.
    assert abs(statistics.median(samples) - 0.69314718056 * mean_ns) / mean_ns < 0.03
    assert min(samples) >= 1


def test_bounded_uniform_interarrival_statistical_and_domain_sanity() -> None:
    source = BoundedUniformInterarrival(
        100,
        300,
        _registry().acquire("traffic/test/uniform-time", owner="statistical-test"),
    )
    samples = [source.next_interval_ns() for _ in range(50_000)]

    assert min(samples) >= 100
    assert max(samples) <= 300
    assert abs(statistics.fmean(samples) - 200) < 1.5


def test_discrete_uniform_packet_size_is_inclusive_and_replayable() -> None:
    source = DiscreteUniformPacketSize(
        10,
        12,
        _registry().acquire("traffic/test/packet-size", owner="size-test"),
    )
    samples = [source.next_payload_bits() for _ in range(500)]
    assert set(samples) == {10, 11, 12}


def test_equal_uniform_bounds_and_constant_size_consume_no_variation() -> None:
    source = BoundedUniformInterarrival(
        25,
        25,
        _registry().acquire("traffic/test/equal", owner="equal-test"),
    )
    assert [source.next_interval_ns() for _ in range(3)] == [25, 25, 25]
    assert ConstantPacketSize(80).next_payload_bits() == 80


def test_generator_rejects_invalid_phase_boundaries() -> None:
    generator = TrafficGenerator(
        bearer=BEARER,
        interarrival=PeriodicInterarrival(10, 0),
        packet_size=ConstantPacketSize(1),
        deadline_ns=None,
    )
    with pytest.raises(InvariantViolation, match="phase boundaries"):
        generator.packets(
            generation_start_tick=10,
            measurement_start_tick=5,
            generation_stop_tick=20,
        )


def test_sub_tick_poisson_quantization_is_observable() -> None:
    source = PoissonInterarrival(
        1,
        _registry().acquire("traffic/test/sub-tick", owner="diagnostic-test"),
    )
    generator = TrafficGenerator(
        bearer=BEARER,
        interarrival=source,
        packet_size=ConstantPacketSize(1),
        deadline_ns=None,
    )
    generator.packets(
        generation_start_tick=0,
        measurement_start_tick=0,
        generation_stop_tick=100,
    )
    diagnostic = generator.diagnostics()[0]
    assert diagnostic.code == "poisson_interarrival_quantized_to_one_tick"
    assert diagnostic.count > 0
