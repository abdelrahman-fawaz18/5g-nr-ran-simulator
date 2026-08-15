"""Typed dynamic-radio extension and canonical unit normalization."""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nr_ran_sim.config.models import FrozenStrictModel, Identifier, QuantityInput
from nr_ran_sim.config.units import QuantityKind, convert_value, require_integral
from nr_ran_sim.errors import ConfigurationValidationError

DYNAMIC_EXTENSION_KEY = "nr-ran-sim.dynamic-radio"


class VelocityInput(FrozenStrictModel):
    x: QuantityInput
    y: QuantityInput
    z: QuantityInput = Field(default_factory=lambda: QuantityInput(value=Decimal(0), unit="m/s"))


class MotionBoundsInput(FrozenStrictModel):
    x_min: QuantityInput
    x_max: QuantityInput
    y_min: QuantityInput
    y_max: QuantityInput


class GroupMotionInput(FrozenStrictModel):
    velocities: tuple[VelocityInput, ...] = Field(min_length=1)
    bounds: MotionBoundsInput


class MobilityInput(FrozenStrictModel):
    profile: Literal["linear-reflect-v1"]
    groups: dict[Identifier, GroupMotionInput] = Field(min_length=1)


class ChannelEvolutionInput(FrozenStrictModel):
    update_interval: QuantityInput
    shadow_correlation_distance: QuantityInput | None = None
    initial_neighbor_load_fraction: Decimal = Field(ge=0, le=1)


class HandoverInput(FrozenStrictModel):
    profile: Literal["a3-inspired-long-term-rsrp-v1"]
    offset: QuantityInput
    hysteresis: QuantityInput
    time_to_trigger: QuantityInput
    interruption: QuantityInput
    ping_pong_window: QuantityInput


class AvailabilityInput(FrozenStrictModel):
    profile: Literal["sinr-hysteresis-availability-v1"]
    outage_threshold: QuantityInput
    recovery_threshold: QuantityInput
    outage_time_to_trigger: QuantityInput
    recovery_time_to_trigger: QuantityInput


class BeamInput(FrozenStrictModel):
    beam_id: Identifier
    boresight_azimuth: QuantityInput
    peak_gain: QuantityInput
    half_power_beamwidth: QuantityInput
    sidelobe_gain: QuantityInput


class BlockageIntervalInput(FrozenStrictModel):
    ue_group_id: Identifier
    ue_ordinal: int = Field(ge=0)
    cell_id: Identifier
    start: QuantityInput
    end: QuantityInput
    excess_loss: QuantityInput


class Fr2AvailabilityInput(FrozenStrictModel):
    beam_codebooks: dict[Identifier, tuple[BeamInput, ...]] = Field(min_length=1)
    blockage_intervals: tuple[BlockageIntervalInput, ...] = ()


class DynamicRadioInput(FrozenStrictModel):
    model_version: Literal["1.0"]
    channel: ChannelEvolutionInput
    mobility: MobilityInput
    handover: HandoverInput
    availability: AvailabilityInput
    fr2: Fr2AvailabilityInput | None = None


class NormalizedDynamicModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NormalizedVelocity(NormalizedDynamicModel):
    x_mps: Decimal
    y_mps: Decimal
    z_mps: Decimal


class NormalizedMotionBounds(NormalizedDynamicModel):
    x_min_m: Decimal
    x_max_m: Decimal
    y_min_m: Decimal
    y_max_m: Decimal


class NormalizedGroupMotion(NormalizedDynamicModel):
    velocities: tuple[NormalizedVelocity, ...]
    bounds: NormalizedMotionBounds


class NormalizedChannelEvolution(NormalizedDynamicModel):
    update_interval_ns: int
    shadow_correlation_distance_m: Decimal | None
    initial_active_prbs: int


class NormalizedHandover(NormalizedDynamicModel):
    profile: str
    offset_db: Decimal
    hysteresis_db: Decimal
    time_to_trigger_ns: int
    interruption_ns: int
    ping_pong_window_ns: int


class NormalizedAvailability(NormalizedDynamicModel):
    profile: str
    outage_threshold_db: Decimal
    recovery_threshold_db: Decimal
    outage_time_to_trigger_ns: int
    recovery_time_to_trigger_ns: int


class NormalizedBeam(NormalizedDynamicModel):
    beam_id: str
    boresight_azimuth_deg: Decimal
    peak_gain_db: Decimal
    half_power_beamwidth_deg: Decimal
    sidelobe_gain_db: Decimal


class NormalizedBlockageInterval(NormalizedDynamicModel):
    ue_id: str
    cell_id: str
    start_ns: int
    end_ns: int
    excess_loss_db: Decimal


class NormalizedFr2Availability(NormalizedDynamicModel):
    beam_codebooks: dict[str, tuple[NormalizedBeam, ...]]
    blockage_intervals: tuple[NormalizedBlockageInterval, ...]


class NormalizedDynamicRadio(NormalizedDynamicModel):
    model_version: Literal["1.0"]
    channel: NormalizedChannelEvolution
    mobility_profile: str
    mobility_groups: dict[str, NormalizedGroupMotion]
    handover: NormalizedHandover
    availability: NormalizedAvailability
    fr2: NormalizedFr2Availability | None


def load_normalized_dynamic_radio(
    extensions: dict[str, object],
) -> NormalizedDynamicRadio | None:
    """Load the already canonical extension stored in a normalized scenario."""

    payload = extensions.get(DYNAMIC_EXTENSION_KEY)
    return None if payload is None else NormalizedDynamicRadio.model_validate(payload)


def normalize_dynamic_radio_extension(
    raw_extensions: dict[str, object],
    *,
    slot_duration_ns: int,
    stop_ns: int,
    prb_count: int,
    frequency_range: str,
    shadowing_model: str,
    group_counts: dict[str, int],
    cell_ids: tuple[str, ...],
) -> NormalizedDynamicRadio | None:
    """Validate and normalize the known dynamic-radio namespace; return ``None`` when absent."""

    raw = raw_extensions.get(DYNAMIC_EXTENSION_KEY)
    if raw is None:
        return None
    try:
        authored = DynamicRadioInput.model_validate(raw)
    except ValueError as exc:
        raise ConfigurationValidationError(
            "invalid nr-ran-sim.dynamic-radio extension",
            {"field": f"extensions.{DYNAMIC_EXTENSION_KEY}", "detail": str(exc)},
        ) from exc

    update_ns = _time_ns(authored.channel.update_interval, "channel.update_interval")
    _require_slot_multiple(update_ns, slot_duration_ns, "channel.update_interval")
    correlation = authored.channel.shadow_correlation_distance
    correlation_m = (
        None
        if correlation is None
        else _positive_distance(correlation, "channel.shadow_correlation_distance")
    )
    if shadowing_model == "correlated_dynamic" and correlation_m is None:
        raise _error(
            "correlated dynamic shadowing requires a correlation distance",
            "channel.shadow_correlation_distance",
            "DYN-CH-003",
        )
    initial_active = int(
        (Decimal(prb_count) * authored.channel.initial_neighbor_load_fraction).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )

    expected_groups = set(group_counts)
    if set(authored.mobility.groups) != expected_groups:
        raise _error(
            "mobility groups must contain exactly the configured UE groups",
            "mobility.groups",
            "DYN-MOB-001",
        )
    mobility_groups: dict[str, NormalizedGroupMotion] = {}
    for group_id, motion in sorted(authored.mobility.groups.items()):
        if len(motion.velocities) != group_counts[group_id]:
            raise _error(
                f"mobility group {group_id!r} requires {group_counts[group_id]} velocities",
                f"mobility.groups.{group_id}.velocities",
                "DYN-MOB-001",
            )
        bounds = NormalizedMotionBounds(
            x_min_m=_distance(motion.bounds.x_min, f"mobility.groups.{group_id}.bounds.x_min"),
            x_max_m=_distance(motion.bounds.x_max, f"mobility.groups.{group_id}.bounds.x_max"),
            y_min_m=_distance(motion.bounds.y_min, f"mobility.groups.{group_id}.bounds.y_min"),
            y_max_m=_distance(motion.bounds.y_max, f"mobility.groups.{group_id}.bounds.y_max"),
        )
        if bounds.x_min_m >= bounds.x_max_m or bounds.y_min_m >= bounds.y_max_m:
            raise _error(
                "mobility bounds must be strictly ordered",
                f"mobility.groups.{group_id}.bounds",
                "DYN-MOB-001",
            )
        velocities = tuple(
            NormalizedVelocity(
                x_mps=_speed(item.x, f"mobility.groups.{group_id}.velocities.{ordinal}.x"),
                y_mps=_speed(item.y, f"mobility.groups.{group_id}.velocities.{ordinal}.y"),
                z_mps=_speed(item.z, f"mobility.groups.{group_id}.velocities.{ordinal}.z"),
            )
            for ordinal, item in enumerate(motion.velocities)
        )
        if any(item.z_mps != 0 for item in velocities):
            raise _error(
                "linear-reflect mobility keeps UE height fixed",
                f"mobility.groups.{group_id}.velocities",
                "DYN-MOB-001",
            )
        mobility_groups[group_id] = NormalizedGroupMotion(velocities=velocities, bounds=bounds)

    handover = NormalizedHandover(
        profile=authored.handover.profile,
        offset_db=_loss(authored.handover.offset, "handover.offset"),
        hysteresis_db=_nonnegative_loss(authored.handover.hysteresis, "handover.hysteresis"),
        time_to_trigger_ns=_aligned_time(
            authored.handover.time_to_trigger, slot_duration_ns, "handover.time_to_trigger"
        ),
        interruption_ns=_aligned_time(
            authored.handover.interruption, slot_duration_ns, "handover.interruption"
        ),
        ping_pong_window_ns=_aligned_time(
            authored.handover.ping_pong_window, slot_duration_ns, "handover.ping_pong_window"
        ),
    )
    availability = NormalizedAvailability(
        profile=authored.availability.profile,
        outage_threshold_db=_loss(
            authored.availability.outage_threshold, "availability.outage_threshold"
        ),
        recovery_threshold_db=_loss(
            authored.availability.recovery_threshold, "availability.recovery_threshold"
        ),
        outage_time_to_trigger_ns=_aligned_time(
            authored.availability.outage_time_to_trigger,
            slot_duration_ns,
            "availability.outage_time_to_trigger",
        ),
        recovery_time_to_trigger_ns=_aligned_time(
            authored.availability.recovery_time_to_trigger,
            slot_duration_ns,
            "availability.recovery_time_to_trigger",
        ),
    )
    if availability.recovery_threshold_db <= availability.outage_threshold_db:
        raise _error(
            "availability recovery threshold must exceed outage threshold",
            "availability",
            "DYN-AVL-002",
        )

    fr2 = _normalize_fr2(
        authored.fr2,
        slot_duration_ns=slot_duration_ns,
        stop_ns=stop_ns,
        group_counts=group_counts,
        cell_ids=cell_ids,
    )
    if frequency_range == "FR2-1" and fr2 is None:
        raise _error("the FR2-1 profile requires beam/blockage configuration", "fr2", "DYN-FR2-003")
    if frequency_range == "FR1" and fr2 is not None:
        raise _error("FR2 beam/blockage configuration is not valid for FR1", "fr2", "DYN-FR2-001")
    return NormalizedDynamicRadio(
        model_version=authored.model_version,
        channel=NormalizedChannelEvolution(
            update_interval_ns=update_ns,
            shadow_correlation_distance_m=correlation_m,
            initial_active_prbs=initial_active,
        ),
        mobility_profile=authored.mobility.profile,
        mobility_groups=mobility_groups,
        handover=handover,
        availability=availability,
        fr2=fr2,
    )


def _normalize_fr2(
    authored: Fr2AvailabilityInput | None,
    *,
    slot_duration_ns: int,
    stop_ns: int,
    group_counts: dict[str, int],
    cell_ids: tuple[str, ...],
) -> NormalizedFr2Availability | None:
    if authored is None:
        return None
    if set(authored.beam_codebooks) != set(cell_ids):
        raise _error(
            "beam codebooks must contain exactly the configured cells",
            "fr2.beam_codebooks",
            "DYN-FR2-003",
        )
    codebooks: dict[str, tuple[NormalizedBeam, ...]] = {}
    for cell_id, beams in sorted(authored.beam_codebooks.items()):
        if not beams:
            raise _error(
                "each FR2 cell requires at least one beam",
                f"fr2.beam_codebooks.{cell_id}",
                "DYN-FR2-003",
            )
        identifiers = [beam.beam_id for beam in beams]
        if len(set(identifiers)) != len(identifiers):
            raise _error(
                "beam identifiers must be unique per cell",
                f"fr2.beam_codebooks.{cell_id}",
                "DYN-FR2-003",
            )
        normalized: list[NormalizedBeam] = []
        for beam in beams:
            width = _angle_deg(beam.half_power_beamwidth, "fr2.beamwidth")
            if not Decimal(0) < width <= Decimal(360):
                raise _error(
                    "beamwidth must be within (0,360] degrees", "fr2.beamwidth", "DYN-FR2-003"
                )
            peak = _loss(beam.peak_gain, "fr2.peak_gain")
            side = _loss(beam.sidelobe_gain, "fr2.sidelobe_gain")
            if side > peak:
                raise _error(
                    "sidelobe gain cannot exceed peak gain", "fr2.sidelobe_gain", "DYN-FR2-003"
                )
            normalized.append(
                NormalizedBeam(
                    beam_id=beam.beam_id,
                    boresight_azimuth_deg=_angle_deg(
                        beam.boresight_azimuth, "fr2.boresight_azimuth"
                    )
                    % Decimal(360),
                    peak_gain_db=peak,
                    half_power_beamwidth_deg=width,
                    sidelobe_gain_db=side,
                )
            )
        codebooks[cell_id] = tuple(sorted(normalized, key=lambda item: item.beam_id))

    intervals: list[NormalizedBlockageInterval] = []
    for ordinal, interval in enumerate(authored.blockage_intervals):
        if interval.ue_group_id not in group_counts or interval.ue_ordinal >= group_counts.get(
            interval.ue_group_id, 0
        ):
            raise _error(
                "blockage interval references an unknown UE",
                f"fr2.blockage_intervals.{ordinal}",
                "DYN-FR2-004",
            )
        if interval.cell_id not in cell_ids:
            raise _error(
                "blockage interval references an unknown cell",
                f"fr2.blockage_intervals.{ordinal}.cell_id",
                "DYN-FR2-004",
            )
        start = _time_ns(interval.start, f"fr2.blockage_intervals.{ordinal}.start", allow_zero=True)
        end = _time_ns(interval.end, f"fr2.blockage_intervals.{ordinal}.end")
        _require_slot_multiple(start, slot_duration_ns, f"fr2.blockage_intervals.{ordinal}.start")
        _require_slot_multiple(end, slot_duration_ns, f"fr2.blockage_intervals.{ordinal}.end")
        if start >= end or end > stop_ns:
            raise _error(
                "blockage interval must satisfy 0 <= start < end <= stop",
                f"fr2.blockage_intervals.{ordinal}",
                "DYN-FR2-004",
            )
        intervals.append(
            NormalizedBlockageInterval(
                ue_id=f"ue/{interval.ue_group_id}/{interval.ue_ordinal:06d}",
                cell_id=f"cell/{interval.cell_id}",
                start_ns=start,
                end_ns=end,
                excess_loss_db=_nonnegative_loss(
                    interval.excess_loss, f"fr2.blockage_intervals.{ordinal}.excess_loss"
                ),
            )
        )
    return NormalizedFr2Availability(
        beam_codebooks=codebooks,
        blockage_intervals=tuple(
            sorted(
                intervals, key=lambda item: (item.start_ns, item.end_ns, item.cell_id, item.ue_id)
            )
        ),
    )


def _quantity(quantity: QuantityInput, kind: QuantityKind, field: str) -> Decimal:
    return convert_value(
        quantity.value, quantity.unit, kind, f"extensions.{DYNAMIC_EXTENSION_KEY}.{field}"
    )


def _time_ns(quantity: QuantityInput, field: str, *, allow_zero: bool = False) -> int:
    value = require_integral(_quantity(quantity, QuantityKind.TIME, field), field, "ns")
    if value < 0 or (value == 0 and not allow_zero):
        raise _error(
            "time must be nonnegative" if allow_zero else "time must be positive", field, "CFG-007"
        )
    return value


def _aligned_time(quantity: QuantityInput, slot_ns: int, field: str) -> int:
    value = _time_ns(quantity, field, allow_zero=True)
    _require_slot_multiple(value, slot_ns, field)
    return value


def _require_slot_multiple(value: int, slot_ns: int, field: str) -> None:
    if value % slot_ns:
        raise _error("dynamic timing must be an integer number of slots", field, "DYN-CH-001")


def _distance(quantity: QuantityInput, field: str) -> Decimal:
    return _quantity(quantity, QuantityKind.DISTANCE, field)


def _positive_distance(quantity: QuantityInput, field: str) -> Decimal:
    value = _distance(quantity, field)
    if value <= 0:
        raise _error("distance must be positive", field, "DYN-CH-003")
    return value


def _speed(quantity: QuantityInput, field: str) -> Decimal:
    return _quantity(quantity, QuantityKind.SPEED, field)


def _loss(quantity: QuantityInput, field: str) -> Decimal:
    return _quantity(quantity, QuantityKind.LOSS, field)


def _nonnegative_loss(quantity: QuantityInput, field: str) -> Decimal:
    value = _loss(quantity, field)
    if value < 0:
        raise _error("loss/hysteresis must be nonnegative", field, "CFG-007")
    return value


def _angle_deg(quantity: QuantityInput, field: str) -> Decimal:
    return _quantity(quantity, QuantityKind.ANGLE, field)


def _error(message: str, field: str, requirement: str) -> ConfigurationValidationError:
    return ConfigurationValidationError(
        message,
        {"field": f"extensions.{DYNAMIC_EXTENSION_KEY}.{field}", "requirement": requirement},
    )
