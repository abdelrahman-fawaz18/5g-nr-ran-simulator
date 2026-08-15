"""Configuration-driven traffic sources with owned semantic RNG streams."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Protocol

from nr_ran_sim.config.normalize import NormalizedTrafficProfile
from nr_ran_sim.domain.entities import BearerRecord
from nr_ran_sim.domain.identifiers import PacketId
from nr_ran_sim.domain.packets import PacketCohort, PacketRecord
from nr_ran_sim.errors import InvariantViolation, RunExecutionError
from nr_ran_sim.experiments.seeds import OwnedRng, SemanticRngRegistry

MAX_TICK = 2**63 - 1
MAX_PACKETS_PER_BEARER = 10_000_000


class InterarrivalSource(Protocol):
    def first_interval_ns(self) -> int: ...

    def next_interval_ns(self) -> int: ...


class PacketSizeSource(Protocol):
    def next_payload_bits(self) -> int: ...


@dataclass(frozen=True, slots=True)
class TrafficSourceDiagnostic:
    bearer_id: str
    code: str
    count: int
    message: str


@dataclass(slots=True)
class PeriodicInterarrival:
    interval_ns: int
    initial_offset_ns: int

    def first_interval_ns(self) -> int:
        return self.initial_offset_ns

    def next_interval_ns(self) -> int:
        return self.interval_ns


@dataclass(slots=True)
class PoissonInterarrival:
    mean_ns: int
    rng: OwnedRng
    minimum_tick_adjustments: int = 0

    def first_interval_ns(self) -> int:
        return self.next_interval_ns()

    def next_interval_ns(self) -> int:
        interval = _round_half_even(self.rng.exponential(float(self.mean_ns)))
        if interval > 0:
            return interval
        self.minimum_tick_adjustments += 1
        return 1


@dataclass(slots=True)
class BoundedUniformInterarrival:
    minimum_ns: int
    maximum_ns: int
    rng: OwnedRng

    def first_interval_ns(self) -> int:
        return self.next_interval_ns()

    def next_interval_ns(self) -> int:
        if self.minimum_ns == self.maximum_ns:
            return self.minimum_ns
        return _round_half_even(self.rng.uniform(float(self.minimum_ns), float(self.maximum_ns)))


@dataclass(slots=True)
class ConstantPacketSize:
    payload_bits: int

    def next_payload_bits(self) -> int:
        return self.payload_bits


@dataclass(slots=True)
class DiscreteUniformPacketSize:
    minimum_bits: int
    maximum_bits: int
    rng: OwnedRng

    def next_payload_bits(self) -> int:
        return self.rng.integer_inclusive(self.minimum_bits, self.maximum_bits)


@dataclass(slots=True)
class TrafficGenerator:
    bearer: BearerRecord
    interarrival: InterarrivalSource
    packet_size: PacketSizeSource
    deadline_ns: int | None

    def diagnostics(self) -> tuple[TrafficSourceDiagnostic, ...]:
        if (
            isinstance(self.interarrival, PoissonInterarrival)
            and self.interarrival.minimum_tick_adjustments
        ):
            return (
                TrafficSourceDiagnostic(
                    bearer_id=str(self.bearer.id),
                    code="poisson_interarrival_quantized_to_one_tick",
                    count=self.interarrival.minimum_tick_adjustments,
                    message=(
                        "continuous exponential draws below half a nanosecond were "
                        "quantized to the minimum positive kernel tick"
                    ),
                ),
            )
        return ()

    def packets(
        self,
        *,
        generation_start_tick: int,
        measurement_start_tick: int,
        generation_stop_tick: int,
    ) -> tuple[PacketRecord, ...]:
        if not 0 <= generation_start_tick <= measurement_start_tick <= generation_stop_tick:
            raise InvariantViolation(
                "traffic generation phase boundaries are invalid",
                {
                    "generation_start_tick": generation_start_tick,
                    "measurement_start_tick": measurement_start_tick,
                    "generation_stop_tick": generation_stop_tick,
                    "requirement": "TIME-008",
                },
            )
        tick = generation_start_tick + self.interarrival.first_interval_ns()
        records: list[PacketRecord] = []
        ordinal = 0
        while tick < generation_stop_tick:
            if ordinal >= MAX_PACKETS_PER_BEARER:
                raise RunExecutionError(
                    "traffic source exceeded the per-bearer safety budget",
                    {
                        "bearer_id": str(self.bearer.id),
                        "packet_budget": MAX_PACKETS_PER_BEARER,
                    },
                )
            payload_bits = self.packet_size.next_payload_bits()
            deadline_tick = None if self.deadline_ns is None else tick + self.deadline_ns
            if tick > MAX_TICK or (deadline_tick is not None and deadline_tick > MAX_TICK):
                raise RunExecutionError(
                    "generated packet time exceeds the signed 64-bit tick domain",
                    {"bearer_id": str(self.bearer.id), "tick": tick},
                )
            records.append(
                PacketRecord(
                    id=PacketId(f"packet/{self.bearer.id.value}/{ordinal:012d}"),
                    bearer_id=self.bearer.id,
                    arrival_tick=tick,
                    payload_bits=payload_bits,
                    deadline_tick=deadline_tick,
                    cohort=(
                        PacketCohort.WARMUP
                        if tick < measurement_start_tick
                        else PacketCohort.MEASUREMENT
                    ),
                )
            )
            ordinal += 1
            interval = self.interarrival.next_interval_ns()
            if interval <= 0:
                raise InvariantViolation(
                    "traffic source produced a nonpositive inter-arrival interval",
                    {"bearer_id": str(self.bearer.id), "requirement": "QOS-004"},
                )
            tick += interval
        return tuple(records)


def build_traffic_generator(
    bearer: BearerRecord,
    profile: NormalizedTrafficProfile,
    rng_registry: SemanticRngRegistry,
) -> TrafficGenerator:
    owner = str(bearer.id)
    source = profile.source
    if source.type == "periodic":
        interarrival: InterarrivalSource = PeriodicInterarrival(
            interval_ns=source.parameters_ns["interval"],
            initial_offset_ns=source.parameters_ns["initial_offset"],
        )
    elif source.type == "poisson":
        interarrival = PoissonInterarrival(
            mean_ns=source.parameters_ns["mean_interarrival"],
            rng=rng_registry.acquire(
                f"traffic/{bearer.id.value}/interarrival",
                owner=owner,
            ),
        )
    elif source.type == "bounded_uniform":
        interarrival = BoundedUniformInterarrival(
            minimum_ns=source.parameters_ns["minimum_interarrival"],
            maximum_ns=source.parameters_ns["maximum_interarrival"],
            rng=rng_registry.acquire(
                f"traffic/{bearer.id.value}/interarrival",
                owner=owner,
            ),
        )
    else:
        raise RunExecutionError(
            "normalized traffic source type is unsupported",
            {"source_type": source.type, "bearer_id": owner},
        )

    size = profile.packet_size
    if size.type == "constant":
        packet_size: PacketSizeSource = ConstantPacketSize(size.parameters_bits["payload"])
    elif size.type == "discrete_uniform":
        packet_size = DiscreteUniformPacketSize(
            minimum_bits=size.parameters_bits["minimum_payload"],
            maximum_bits=size.parameters_bits["maximum_payload"],
            rng=rng_registry.acquire(
                f"traffic/{bearer.id.value}/packet-size",
                owner=owner,
            ),
        )
    else:
        raise RunExecutionError(
            "normalized packet-size source type is unsupported",
            {"packet_size_type": size.type, "bearer_id": owner},
        )
    return TrafficGenerator(
        bearer=bearer,
        interarrival=interarrival,
        packet_size=packet_size,
        deadline_ns=profile.deadline_ns,
    )


def _round_half_even(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
