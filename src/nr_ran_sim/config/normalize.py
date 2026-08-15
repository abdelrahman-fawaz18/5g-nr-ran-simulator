"""Semantic validation and one-way normalization into canonical runtime values."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

from nr_ran_sim.config.dynamic import DYNAMIC_EXTENSION_KEY, normalize_dynamic_radio_extension
from nr_ran_sim.config.models import (
    BoundedUniformSource,
    ConstantPacketSize,
    ExplicitPlacement,
    PeriodicSource,
    PoissonSource,
    PositionConfig,
    QuantityInput,
    ScenarioConfig,
    TrafficProfileConfig,
    UniformPacketSize,
)
from nr_ran_sim.config.units import QuantityKind, convert_value, require_integral
from nr_ran_sim.errors import ConfigurationValidationError

MAX_TICK: Final = 2**63 - 1
EXTENSION_NAMESPACE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$")
SECRET_TERMS: Final = frozenset({"credential", "password", "secret", "token"})

# TS 38.104 V18.12.0 Table 5.3.2-1. Values are configuration-domain data;
# The NR capacity layer consumes the same table for capacity/resource behavior.
FR1_PRB_TABLE: Final[dict[int, dict[int, int]]] = {
    15_000: {
        3: 15,
        5: 25,
        10: 52,
        15: 79,
        20: 106,
        25: 133,
        30: 160,
        35: 188,
        40: 216,
        45: 242,
        50: 270,
    },
    30_000: {
        5: 11,
        10: 24,
        15: 38,
        20: 51,
        25: 65,
        30: 78,
        35: 92,
        40: 106,
        45: 119,
        50: 133,
        60: 162,
        70: 189,
        80: 217,
        90: 245,
        100: 273,
    },
    60_000: {
        10: 11,
        15: 18,
        20: 24,
        25: 31,
        30: 38,
        35: 44,
        40: 51,
        45: 58,
        50: 65,
        60: 79,
        70: 93,
        80: 107,
        90: 121,
        100: 135,
    },
}

# TS 38.104 V18.12.0 Table 5.3.2-2 (FR2-1).
FR2_1_PRB_TABLE: Final[dict[int, dict[int, int]]] = {
    60_000: {50: 66, 100: 132, 200: 264},
    120_000: {50: 32, 100: 66, 200: 132, 400: 264},
}


class NormalizedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NormalizedSimulation(NormalizedModel):
    warmup_ns: int
    measurement_ns: int
    drain_ns: int
    measurement_start_ns: int
    measurement_end_ns: int
    stop_ns: int


class NormalizedRadio(NormalizedModel):
    direction: Literal["downlink"]
    frequency_range: Literal["FR1", "FR2-1"]
    carrier_frequency_hz: Decimal
    channel_bandwidth_hz: int
    subcarrier_spacing_hz: int
    numerology: int
    cyclic_prefix: Literal["normal"]
    slots_per_ms: int
    slot_duration_ns: int
    prb_count: int
    transmission_bandwidth_hz: int
    layers: Literal[1]
    cqi_table: Literal["table1"]
    mcs_table: Literal["table1"]
    target_bler: Decimal
    implementation_margin_db: Decimal
    data_re_overhead_fraction: Decimal


class NormalizedModels(NormalizedModel):
    fidelity_profile: str
    propagation: str
    los_state: str
    shadowing: str
    interference: str
    link_adaptation: str


class NormalizedPosition(NormalizedModel):
    x_m: Decimal
    y_m: Decimal
    z_m: Decimal


class NormalizedCell(NormalizedModel):
    position: NormalizedPosition
    transmit_power_w: Decimal
    transmit_power_dbm: Decimal
    antenna_gain_dbi: Decimal
    miscellaneous_loss_db: Decimal


class NormalizedPlacement(NormalizedModel):
    mode: Literal["uniform_rectangle"]
    x_min_m: Decimal
    x_max_m: Decimal
    y_min_m: Decimal
    y_max_m: Decimal
    height_m: Decimal
    minimum_2d_distance_m: Decimal
    attempt_budget: int


class NormalizedExplicitPlacement(NormalizedModel):
    mode: Literal["explicit"]
    positions: tuple[NormalizedPosition, ...]
    minimum_2d_distance_m: Decimal


class NormalizedUEGroup(NormalizedModel):
    count: int
    placement: NormalizedPlacement | NormalizedExplicitPlacement
    receiver_noise_figure_db: Decimal
    antenna_gain_dbi: Decimal
    penetration_loss_db: Decimal
    explicit_link_states: dict[str, tuple[str, ...]] | None
    bearers: tuple[str, ...]


class NormalizedTopology(NormalizedModel):
    scenario: str
    coordinate_system: Literal["local-cartesian"]
    average_building_height_m: Decimal | None
    average_street_width_m: Decimal | None
    cells: dict[str, NormalizedCell]
    ue_groups: dict[str, NormalizedUEGroup]


class NormalizedSource(NormalizedModel):
    type: str
    parameters_ns: dict[str, int]


class NormalizedPacketSize(NormalizedModel):
    type: str
    parameters_bits: dict[str, int]


class NormalizedQueue(NormalizedModel):
    max_packets: int | None
    max_payload_bits: int | None


class NormalizedTrafficProfile(NormalizedModel):
    source: NormalizedSource
    packet_size: NormalizedPacketSize
    queue: NormalizedQueue
    deadline_ns: int | None
    qos_reference_5qi: int | None


class NormalizedScheduler(NormalizedModel):
    policy: str
    averaging_alpha: Decimal | None
    initial_rate_floor_bps: Decimal | None


class NormalizedWarning(NormalizedModel):
    code: str
    requirement: str
    message: str
    context: dict[str, str]


class NormalizedScenario(NormalizedModel):
    normalized_schema_version: Literal["1.0"] = "1.0"
    source_schema_version: Literal["1.0"]
    scenario_id: str
    description: str
    simulation: NormalizedSimulation
    radio: NormalizedRadio
    models: NormalizedModels
    topology: NormalizedTopology
    traffic_profiles: dict[str, NormalizedTrafficProfile]
    scheduler: NormalizedScheduler
    extensions: dict[str, Any]
    warnings: tuple[NormalizedWarning, ...]


def normalize_scenario(config: ScenarioConfig) -> NormalizedScenario:
    """Normalize a validated authoring model and enforce cross-field semantics."""

    simulation = _normalize_simulation(config)
    _validate_profile_compatibility(config)
    radio = _normalize_radio(config)
    traffic = {
        profile_id: _normalize_traffic(profile_id, profile)
        for profile_id, profile in sorted(config.traffic_profiles.items())
    }
    topology = _normalize_topology(config)
    scheduler = _normalize_scheduler(config)
    warnings = _build_warnings(simulation, traffic)
    _validate_extensions(config.extensions)
    dynamic = normalize_dynamic_radio_extension(
        config.extensions,
        slot_duration_ns=radio.slot_duration_ns,
        stop_ns=simulation.stop_ns,
        prb_count=radio.prb_count,
        frequency_range=radio.frequency_range,
        shadowing_model=config.models.shadowing,
        group_counts={group_id: group.count for group_id, group in topology.ue_groups.items()},
        cell_ids=tuple(topology.cells),
    )
    if dynamic is not None and topology.scenario == "uma":
        for group_id, group in topology.ue_groups.items():
            heights = (
                (group.placement.height_m,)
                if isinstance(group.placement, NormalizedPlacement)
                else tuple(position.z_m for position in group.placement.positions)
            )
            if any(height > Decimal(13) for height in heights):
                raise ConfigurationValidationError(
                    "dynamic UMa profiles currently require UE height at or below 13 m",
                    {
                        "field": f"topology.ue_groups.{group_id}.placement",
                        "requirement": "DYN-CH-004",
                    },
                )
    normalized_extensions = {
        key: value
        for key, value in sorted(config.extensions.items())
        if key != DYNAMIC_EXTENSION_KEY
    }
    if dynamic is not None:
        normalized_extensions[DYNAMIC_EXTENSION_KEY] = dynamic.model_dump(mode="json")
    return NormalizedScenario(
        source_schema_version=config.schema_version,
        scenario_id=config.scenario_id,
        description=config.description,
        simulation=simulation,
        radio=radio,
        models=NormalizedModels(**config.models.model_dump()),
        topology=topology,
        traffic_profiles=traffic,
        scheduler=scheduler,
        extensions=normalized_extensions,
        warnings=warnings,
    )


def _normalize_simulation(config: ScenarioConfig) -> NormalizedSimulation:
    warmup = _time_ns(config.simulation.warmup, "simulation.warmup", allow_zero=True)
    measurement = _time_ns(config.simulation.measurement, "simulation.measurement")
    drain = _time_ns(config.simulation.drain, "simulation.drain", allow_zero=True)
    measurement_end = warmup + measurement
    stop = measurement_end + drain
    if stop > MAX_TICK:
        raise ConfigurationValidationError(
            "simulation stop tick exceeds the supported signed 64-bit range",
            {"field": "simulation", "stop_ns": stop, "requirement": "CFG-007"},
        )
    return NormalizedSimulation(
        warmup_ns=warmup,
        measurement_ns=measurement,
        drain_ns=drain,
        measurement_start_ns=warmup,
        measurement_end_ns=measurement_end,
        stop_ns=stop,
    )


def _normalize_radio(config: ScenarioConfig) -> NormalizedRadio:
    radio = config.radio
    carrier_hz = _quantity(
        radio.carrier_frequency, QuantityKind.FREQUENCY, "radio.carrier_frequency"
    )
    carrier_domain = (
        (Decimal("500000000"), Decimal("7125000000"))
        if radio.frequency_range == "FR1"
        else (Decimal("24250000000"), Decimal("52600000000"))
    )
    if not carrier_domain[0] <= carrier_hz <= carrier_domain[1]:
        raise ConfigurationValidationError(
            f"carrier frequency is outside the configured {radio.frequency_range} domain",
            {
                "field": "radio.carrier_frequency",
                "value_hz": str(carrier_hz),
                "requirement": "CFG-007",
                "expected_hz": f"{carrier_domain[0]}-{carrier_domain[1]}",
                "standard_trace": (
                    "STD-FR-001" if radio.frequency_range == "FR1" else "STD-FR2-001"
                ),
            },
        )
    bandwidth_hz = require_integral(
        _quantity(radio.channel_bandwidth, QuantityKind.FREQUENCY, "radio.channel_bandwidth"),
        "radio.channel_bandwidth",
        "Hz",
    )
    scs_hz = require_integral(
        _quantity(radio.subcarrier_spacing, QuantityKind.FREQUENCY, "radio.subcarrier_spacing"),
        "radio.subcarrier_spacing",
        "Hz",
    )
    bandwidth_mhz, remainder = divmod(bandwidth_hz, 1_000_000)
    prb_table = FR1_PRB_TABLE if radio.frequency_range == "FR1" else FR2_1_PRB_TABLE
    if remainder or scs_hz not in prb_table or bandwidth_mhz not in prb_table[scs_hz]:
        raise ConfigurationValidationError(
            f"unsupported {radio.frequency_range} channel-bandwidth/subcarrier-spacing combination",
            {
                "field": "radio",
                "channel_bandwidth_hz": bandwidth_hz,
                "subcarrier_spacing_hz": scs_hz,
                "requirement": "CFG-007",
                "standard_trace": (
                    "STD-RB-001" if radio.frequency_range == "FR1" else "STD-FR2-001"
                ),
            },
        )
    prbs = prb_table[scs_hz][bandwidth_mhz]
    numerology = {15_000: 0, 30_000: 1, 60_000: 2, 120_000: 3}[scs_hz]
    slots_per_ms = 2**numerology
    margin = _quantity(
        radio.implementation_margin, QuantityKind.LOSS, "radio.implementation_margin"
    )
    return NormalizedRadio(
        direction=radio.direction,
        frequency_range=radio.frequency_range,
        carrier_frequency_hz=carrier_hz,
        channel_bandwidth_hz=bandwidth_hz,
        subcarrier_spacing_hz=scs_hz,
        numerology=numerology,
        cyclic_prefix=radio.cyclic_prefix,
        slots_per_ms=slots_per_ms,
        slot_duration_ns=1_000_000 // slots_per_ms,
        prb_count=prbs,
        transmission_bandwidth_hz=prbs * 12 * scs_hz,
        layers=radio.layers,
        cqi_table=radio.cqi_table,
        mcs_table=radio.mcs_table,
        target_bler=radio.target_bler,
        implementation_margin_db=margin,
        data_re_overhead_fraction=radio.data_re_overhead_fraction,
    )


def _validate_profile_compatibility(config: ScenarioConfig) -> None:
    profile = config.models.fidelity_profile
    dynamic_extension = config.extensions.get("nr-ran-sim.dynamic-radio")
    if profile == "tier-a-fr1-static-v1":
        if config.radio.frequency_range != "FR1":
            raise ConfigurationValidationError(
                "the Tier A static profile supports FR1 only",
                {"field": "radio.frequency_range", "requirement": "CFG-007"},
            )
        if config.models.shadowing == "correlated_dynamic" or (
            config.models.interference == "activity-coupled-reuse1-v1"
        ):
            raise ConfigurationValidationError(
                "dynamic shadow/interference requires an explicit dynamic-radio profile",
                {"field": "models", "requirement": "PROP-008"},
            )
        if dynamic_extension is not None:
            raise ConfigurationValidationError(
                "nr-ran-sim.dynamic-radio is incompatible with the static Tier A profile",
                {"field": "extensions.nr-ran-sim.dynamic-radio", "requirement": "DYN-REP-003"},
            )
        return

    if dynamic_extension is None:
        raise ConfigurationValidationError(
            "a dynamic fidelity profile requires extensions.nr-ran-sim.dynamic-radio",
            {"field": "extensions.nr-ran-sim.dynamic-radio", "requirement": "DYN-CH-001"},
        )
    if profile == "tier-b-fr1-dynamic-v1" and config.radio.frequency_range != "FR1":
        raise ConfigurationValidationError(
            "tier-b-fr1-dynamic-v1 requires FR1",
            {"field": "radio.frequency_range", "requirement": "CFG-007"},
        )
    if config.models.interference != "activity-coupled-reuse1-v1":
        raise ConfigurationValidationError(
            "dynamic fidelity profiles require activity-coupled interference",
            {"field": "models.interference", "requirement": "DYN-INT-001"},
        )
    if config.models.shadowing != "correlated_dynamic":
        raise ConfigurationValidationError(
            "dynamic fidelity profiles require correlated dynamic shadowing",
            {"field": "models.shadowing", "requirement": "DYN-CH-002"},
        )
    if profile == "tier-b-fr2-availability-v1":
        if config.radio.frequency_range != "FR2-1":
            raise ConfigurationValidationError(
                "tier-b-fr2-availability-v1 requires FR2-1",
                {"field": "radio.frequency_range", "requirement": "DYN-FR2-001"},
            )
        if config.topology.scenario == "rma":
            raise ConfigurationValidationError(
                "the bounded FR2 profile supports UMa and UMi-street-canyon only",
                {"field": "topology.scenario", "requirement": "DYN-FR2-002"},
            )


def _normalize_topology(config: ScenarioConfig) -> NormalizedTopology:
    scenario = config.topology.scenario
    environment = config.topology.propagation_environment
    average_building_height: Decimal | None = None
    average_street_width: Decimal | None = None
    if environment is not None:
        average_building_height = _quantity(
            environment.average_building_height,
            QuantityKind.DISTANCE,
            "topology.propagation_environment.average_building_height",
        )
        average_street_width = _quantity(
            environment.average_street_width,
            QuantityKind.DISTANCE,
            "topology.propagation_environment.average_street_width",
        )
        for field, value in (
            ("average_building_height", average_building_height),
            ("average_street_width", average_street_width),
        ):
            if not Decimal(5) <= value <= Decimal(50):
                raise ConfigurationValidationError(
                    f"RMa {field} must be within 5-50 m",
                    {
                        "field": f"topology.propagation_environment.{field}",
                        "value_m": str(value),
                        "requirement": "PROP-004",
                        "standard_trace": "STD-PL-001",
                    },
                )
    cells: dict[str, NormalizedCell] = {}
    for cell_id, cell in sorted(config.topology.cells.items()):
        position = _position(cell.position, f"topology.cells.{cell_id}.position")
        if position.z_m <= 0:
            raise _positive_error(f"topology.cells.{cell_id}.position.z", position.z_m)
        _validate_antenna_height(
            scenario,
            position.z_m,
            field=f"topology.cells.{cell_id}.position.z",
            is_cell=True,
        )
        watts, dbm = _power(cell.transmit_power, f"topology.cells.{cell_id}.transmit_power")
        loss = _quantity(
            cell.miscellaneous_loss,
            QuantityKind.LOSS,
            f"topology.cells.{cell_id}.miscellaneous_loss",
        )
        if loss < 0:
            raise _nonnegative_error(f"topology.cells.{cell_id}.miscellaneous_loss", loss)
        cells[cell_id] = NormalizedCell(
            position=position,
            transmit_power_w=watts,
            transmit_power_dbm=dbm,
            antenna_gain_dbi=_quantity(
                cell.antenna_gain,
                QuantityKind.GAIN,
                f"topology.cells.{cell_id}.antenna_gain",
            ),
            miscellaneous_loss_db=loss,
        )
    groups: dict[str, NormalizedUEGroup] = {}
    for group_id, group in sorted(config.topology.ue_groups.items()):
        prefix = f"topology.ue_groups.{group_id}"
        placement = group.placement
        minimum_distance = (
            Decimal(0)
            if placement.minimum_2d_distance is None
            else _quantity(
                placement.minimum_2d_distance,
                QuantityKind.DISTANCE,
                f"{prefix}.placement.minimum_2d_distance",
            )
        )
        if minimum_distance < 0:
            raise _nonnegative_error(f"{prefix}.placement.minimum_2d_distance", minimum_distance)
        if isinstance(placement, ExplicitPlacement):
            positions = tuple(
                _position(position, f"{prefix}.placement.positions.{ordinal}")
                for ordinal, position in enumerate(placement.positions)
            )
            for ordinal, position in enumerate(positions):
                _validate_antenna_height(
                    scenario,
                    position.z_m,
                    field=f"{prefix}.placement.positions.{ordinal}.z",
                    is_cell=False,
                )
                _validate_explicit_minimum_distance(
                    position,
                    cells,
                    minimum_distance,
                    f"{prefix}.placement.positions.{ordinal}",
                )
            normalized_placement: NormalizedPlacement | NormalizedExplicitPlacement = (
                NormalizedExplicitPlacement(
                    mode="explicit",
                    positions=positions,
                    minimum_2d_distance_m=minimum_distance,
                )
            )
        else:
            x_min = _quantity(placement.x_min, QuantityKind.DISTANCE, f"{prefix}.placement.x_min")
            x_max = _quantity(placement.x_max, QuantityKind.DISTANCE, f"{prefix}.placement.x_max")
            y_min = _quantity(placement.y_min, QuantityKind.DISTANCE, f"{prefix}.placement.y_min")
            y_max = _quantity(placement.y_max, QuantityKind.DISTANCE, f"{prefix}.placement.y_max")
            height = _quantity(
                placement.height, QuantityKind.DISTANCE, f"{prefix}.placement.height"
            )
            if x_min >= x_max or y_min >= y_max:
                raise ConfigurationValidationError(
                    f"{prefix}.placement bounds must be strictly ordered",
                    {"field": f"{prefix}.placement", "requirement": "CFG-007"},
                )
            _validate_antenna_height(
                scenario,
                height,
                field=f"{prefix}.placement.height",
                is_cell=False,
            )
            normalized_placement = NormalizedPlacement(
                mode=placement.mode,
                x_min_m=x_min,
                x_max_m=x_max,
                y_min_m=y_min,
                y_max_m=y_max,
                height_m=height,
                minimum_2d_distance_m=minimum_distance,
                attempt_budget=placement.attempt_budget,
            )
        noise_figure = _quantity(
            group.receiver_noise_figure,
            QuantityKind.LOSS,
            f"{prefix}.receiver_noise_figure",
        )
        if noise_figure < 0:
            raise _nonnegative_error(f"{prefix}.receiver_noise_figure", noise_figure)
        penetration_loss = _quantity(
            group.penetration_loss,
            QuantityKind.LOSS,
            f"{prefix}.penetration_loss",
        )
        if penetration_loss < 0:
            raise _nonnegative_error(f"{prefix}.penetration_loss", penetration_loss)
        groups[group_id] = NormalizedUEGroup(
            count=group.count,
            placement=normalized_placement,
            receiver_noise_figure_db=noise_figure,
            antenna_gain_dbi=_quantity(
                group.antenna_gain,
                QuantityKind.GAIN,
                f"{prefix}.antenna_gain",
            ),
            penetration_loss_db=penetration_loss,
            explicit_link_states=(
                None
                if group.explicit_link_states is None
                else {
                    cell_id: tuple(states)
                    for cell_id, states in sorted(group.explicit_link_states.items())
                }
            ),
            bearers=tuple(group.bearers),
        )
    return NormalizedTopology(
        scenario=scenario,
        coordinate_system=config.topology.coordinate_system,
        average_building_height_m=average_building_height,
        average_street_width_m=average_street_width,
        cells=cells,
        ue_groups=groups,
    )


def _validate_antenna_height(
    scenario: str,
    height_m: Decimal,
    *,
    field: str,
    is_cell: bool,
) -> None:
    if scenario == "rma":
        lower, upper = (Decimal(10), Decimal(150)) if is_cell else (Decimal(1), Decimal(10))
        valid = lower <= height_m <= upper
        expected = f"{lower}-{upper} m"
        standard_trace = "STD-PL-001"
    elif scenario == "uma":
        valid = (
            height_m == Decimal(25) if is_cell else Decimal("1.5") <= height_m <= Decimal("22.5")
        )
        expected = "25 m" if is_cell else "1.5-22.5 m"
        standard_trace = "STD-PL-002"
    else:
        valid = (
            height_m == Decimal(10) if is_cell else Decimal("1.5") <= height_m <= Decimal("22.5")
        )
        expected = "10 m" if is_cell else "1.5-22.5 m"
        standard_trace = "STD-PL-003"
    if not valid:
        raise ConfigurationValidationError(
            f"{scenario} antenna height is outside the path-loss model domain",
            {
                "field": field,
                "value_m": str(height_m),
                "expected": expected,
                "requirement": "PROP-004",
                "standard_trace": standard_trace,
            },
        )


def _validate_explicit_minimum_distance(
    position: NormalizedPosition,
    cells: dict[str, NormalizedCell],
    minimum_distance_m: Decimal,
    field: str,
) -> None:
    for cell_id, cell in cells.items():
        dx = position.x_m - cell.position.x_m
        dy = position.y_m - cell.position.y_m
        distance = (dx * dx + dy * dy).sqrt()
        if distance < minimum_distance_m:
            raise ConfigurationValidationError(
                "explicit UE position violates its minimum 2D cell distance",
                {
                    "field": field,
                    "cell_id": cell_id,
                    "distance_m": str(distance),
                    "minimum_distance_m": str(minimum_distance_m),
                    "requirement": "PROP-011",
                },
            )


def _normalize_traffic(
    profile_id: str,
    profile: TrafficProfileConfig,
) -> NormalizedTrafficProfile:
    prefix = f"traffic_profiles.{profile_id}"
    source = profile.source
    if isinstance(source, PeriodicSource):
        parameters = {"interval": _time_ns(source.interval, f"{prefix}.source.interval")}
        parameters["initial_offset"] = (
            0
            if source.initial_offset is None
            else _time_ns(source.initial_offset, f"{prefix}.source.initial_offset", allow_zero=True)
        )
    elif isinstance(source, PoissonSource):
        parameters = {
            "mean_interarrival": _time_ns(
                source.mean_interarrival,
                f"{prefix}.source.mean_interarrival",
            )
        }
    elif isinstance(source, BoundedUniformSource):
        minimum = _time_ns(source.minimum_interarrival, f"{prefix}.source.minimum_interarrival")
        maximum = _time_ns(source.maximum_interarrival, f"{prefix}.source.maximum_interarrival")
        if minimum > maximum:
            raise ConfigurationValidationError(
                f"{prefix}.source inter-arrival bounds are reversed",
                {"field": f"{prefix}.source", "requirement": "QOS-004"},
            )
        parameters = {"minimum_interarrival": minimum, "maximum_interarrival": maximum}
    else:  # pragma: no cover - discriminated union makes this unreachable
        raise TypeError("unknown source type")

    size = profile.packet_size
    if isinstance(size, ConstantPacketSize):
        size_parameters = {"payload": _data_bits(size.payload, f"{prefix}.packet_size.payload")}
    elif isinstance(size, UniformPacketSize):
        minimum_bits = _data_bits(size.minimum_payload, f"{prefix}.packet_size.minimum_payload")
        maximum_bits = _data_bits(size.maximum_payload, f"{prefix}.packet_size.maximum_payload")
        if minimum_bits > maximum_bits:
            raise ConfigurationValidationError(
                f"{prefix}.packet_size bounds are reversed",
                {"field": f"{prefix}.packet_size", "requirement": "QOS-004"},
            )
        size_parameters = {"minimum_payload": minimum_bits, "maximum_payload": maximum_bits}
    else:  # pragma: no cover - discriminated union makes this unreachable
        raise TypeError("unknown packet-size type")

    max_payload = (
        None
        if profile.queue.max_payload is None
        else _data_bits(profile.queue.max_payload, f"{prefix}.queue.max_payload")
    )
    deadline = (
        None if profile.deadline is None else _time_ns(profile.deadline, f"{prefix}.deadline")
    )
    return NormalizedTrafficProfile(
        source=NormalizedSource(type=source.type, parameters_ns=parameters),
        packet_size=NormalizedPacketSize(type=size.type, parameters_bits=size_parameters),
        queue=NormalizedQueue(
            max_packets=profile.queue.max_packets,
            max_payload_bits=max_payload,
        ),
        deadline_ns=deadline,
        qos_reference_5qi=profile.qos_reference_5qi,
    )


def _normalize_scheduler(config: ScenarioConfig) -> NormalizedScheduler:
    scheduler = config.scheduler
    floor = scheduler.parameters.initial_rate_floor
    return NormalizedScheduler(
        policy=scheduler.policy,
        averaging_alpha=scheduler.parameters.averaging_alpha,
        initial_rate_floor_bps=(
            None
            if floor is None
            else _quantity(floor, QuantityKind.RATE, "scheduler.parameters.initial_rate_floor")
        ),
    )


def _build_warnings(
    simulation: NormalizedSimulation,
    traffic: dict[str, NormalizedTrafficProfile],
) -> tuple[NormalizedWarning, ...]:
    maximum_deadline = max(
        (profile.deadline_ns or 0 for profile in traffic.values()),
        default=0,
    )
    if maximum_deadline <= simulation.drain_ns:
        return ()
    return (
        NormalizedWarning(
            code="drain_shorter_than_maximum_deadline",
            requirement="KPI-002",
            message=(
                "drain duration is shorter than the maximum packet deadline; "
                "deadline conclusions must disclose censoring"
            ),
            context={
                "drain_ns": str(simulation.drain_ns),
                "maximum_deadline_ns": str(maximum_deadline),
            },
        ),
    )


def _validate_extensions(extensions: dict[str, Any]) -> None:
    for namespace, value in extensions.items():
        if not EXTENSION_NAMESPACE.fullmatch(namespace):
            raise ConfigurationValidationError(
                "extension keys must be namespaced, for example 'research.example'",
                {"field": f"extensions.{namespace}", "requirement": "CFG-002"},
            )
        lowered = namespace.lower()
        if any(term in lowered for term in SECRET_TERMS) or _contains_absolute_path_or_secret(
            value
        ):
            raise ConfigurationValidationError(
                "extensions must not contain secrets or machine-specific absolute paths",
                {"field": f"extensions.{namespace}", "requirement": "CFG-010"},
            )


def _contains_absolute_path_or_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            any(term in str(key).lower() for term in SECRET_TERMS)
            or _contains_absolute_path_or_secret(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_absolute_path_or_secret(item) for item in value)
    if isinstance(value, str):
        return value.startswith(("/", "\\\\")) or bool(re.match(r"^[A-Za-z]:[\\/]", value))
    return False


def _position(position: PositionConfig, prefix: str) -> NormalizedPosition:
    return NormalizedPosition(
        x_m=_quantity(position.x, QuantityKind.DISTANCE, f"{prefix}.x"),
        y_m=_quantity(position.y, QuantityKind.DISTANCE, f"{prefix}.y"),
        z_m=_quantity(position.z, QuantityKind.DISTANCE, f"{prefix}.z"),
    )


def _power(quantity: QuantityInput, field: str) -> tuple[Decimal, Decimal]:
    watts = _quantity(quantity, QuantityKind.POWER, field)
    if watts <= 0:
        raise _positive_error(field, watts)
    dbm = Decimal(10) * watts.ln() / Decimal(10).ln() + Decimal(30)
    return watts, dbm


def _time_ns(quantity: QuantityInput, field: str, *, allow_zero: bool = False) -> int:
    value = require_integral(_quantity(quantity, QuantityKind.TIME, field), field, "ns")
    if value < 0 or (value == 0 and not allow_zero):
        relation = "nonnegative" if allow_zero else "strictly positive"
        raise ConfigurationValidationError(
            f"{field} must be {relation}",
            {"field": field, "value_ns": value, "requirement": "CFG-007"},
        )
    return value


def _data_bits(quantity: QuantityInput, field: str) -> int:
    value = require_integral(_quantity(quantity, QuantityKind.DATA, field), field, "bit")
    if value <= 0:
        raise _positive_error(field, Decimal(value))
    return value


def _quantity(quantity: QuantityInput, kind: QuantityKind, field: str) -> Decimal:
    return convert_value(quantity.value, quantity.unit, kind, field)


def _positive_error(field: str, value: Decimal) -> ConfigurationValidationError:
    return ConfigurationValidationError(
        f"{field} must be strictly positive",
        {"field": field, "value": str(value), "requirement": "CFG-007"},
    )


def _nonnegative_error(field: str, value: Decimal) -> ConfigurationValidationError:
    return ConfigurationValidationError(
        f"{field} must be nonnegative",
        {"field": field, "value": str(value), "requirement": "CFG-007"},
    )
