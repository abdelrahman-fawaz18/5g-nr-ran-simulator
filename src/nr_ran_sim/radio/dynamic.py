"""Deterministic mobility, channel, interference, and availability models."""

from __future__ import annotations

import math
from dataclasses import dataclass

from nr_ran_sim.config.dynamic import (
    NormalizedAvailability,
    NormalizedBeam,
    NormalizedBlockageInterval,
    NormalizedHandover,
    NormalizedMotionBounds,
)
from nr_ran_sim.errors import ModelDomainError
from nr_ran_sim.radio.geometry import Position3D
from nr_ran_sim.radio.link import LinkBudgetResult, dbm_to_watt, watt_to_dbm

ACTIVITY_INTERFERENCE_PROFILE_ID = "activity-coupled-reuse1-v1"
MOTION_PROFILE_ID = "linear-reflect-v1"
SHADOW_EVOLUTION_PROFILE_ID = "distance-gauss-markov-shadow-v1"
BEAM_PROFILE_ID = "horizontal-parabolic-codebook-v1"
BLOCKAGE_PROFILE_ID = "explicit-link-interval-blockage-v1"


@dataclass(frozen=True, slots=True)
class Velocity3D:
    x_mps: float
    y_mps: float
    z_mps: float = 0.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.x_mps, self.y_mps, self.z_mps)):
            raise ModelDomainError(
                "mobility velocity must be finite",
                {"requirement": "DYN-MOB-001"},
            )
        if self.z_mps != 0.0:
            raise ModelDomainError(
                "linear-reflect-v1 keeps UE height fixed",
                {"z_mps": self.z_mps, "requirement": "DYN-MOB-001"},
            )

    def as_dict(self) -> dict[str, float]:
        return {"x_mps": self.x_mps, "y_mps": self.y_mps, "z_mps": self.z_mps}


@dataclass(frozen=True, slots=True)
class MotionState:
    position: Position3D
    velocity: Velocity3D

    def as_dict(self) -> dict[str, object]:
        return {"position": self.position.as_dict(), "velocity": self.velocity.as_dict()}


@dataclass(frozen=True, slots=True)
class ShadowEvolution:
    value_db: float
    rho: float
    innovation_standard_normal: float
    travelled_distance_m: float

    def as_dict(self) -> dict[str, float]:
        return {
            "value_db": self.value_db,
            "rho": self.rho,
            "innovation_standard_normal": self.innovation_standard_normal,
            "travelled_distance_m": self.travelled_distance_m,
        }


@dataclass(frozen=True, slots=True)
class BeamSelection:
    profile_id: str
    beam_id: str
    link_azimuth_deg: float
    wrapped_offset_deg: float
    gain_db: float

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "beam_id": self.beam_id,
            "link_azimuth_deg": self.link_azimuth_deg,
            "wrapped_offset_deg": self.wrapped_offset_deg,
            "gain_db": self.gain_db,
        }


@dataclass(frozen=True, slots=True)
class BlockageState:
    profile_id: str
    blocked: bool
    excess_loss_db: float

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "blocked": self.blocked,
            "excess_loss_db": self.excess_loss_db,
        }


@dataclass(frozen=True, slots=True)
class ActivityInterferenceComponent:
    cell_id: str
    active_prbs: int
    overlap_prbs: int
    power_w: float
    power_dbm: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "active_prbs": self.active_prbs,
            "overlap_prbs": self.overlap_prbs,
            "power_w": self.power_w,
            "power_dbm": self.power_dbm,
        }


@dataclass(frozen=True, slots=True)
class ActivitySinrResult:
    profile_id: str
    allocated_prbs: int
    prb_bandwidth_hz: int
    signal_power_w: float
    noise_power_w: float
    interference_power_w: float
    sinr_linear: float
    sinr_db: float
    components: tuple[ActivityInterferenceComponent, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "allocated_prbs": self.allocated_prbs,
            "prb_bandwidth_hz": self.prb_bandwidth_hz,
            "signal_power_w": self.signal_power_w,
            "signal_power_dbm": watt_to_dbm(self.signal_power_w),
            "noise_power_w": self.noise_power_w,
            "noise_power_dbm": watt_to_dbm(self.noise_power_w),
            "interference_power_w": self.interference_power_w,
            "interference_power_dbm": (
                None if self.interference_power_w == 0 else watt_to_dbm(self.interference_power_w)
            ),
            "sinr_linear": self.sinr_linear,
            "sinr_db": self.sinr_db,
            "components": [item.as_dict() for item in self.components],
        }


@dataclass(frozen=True, slots=True)
class HandoverState:
    serving_cell_id: str
    pending_cell_id: str | None = None
    pending_since_tick: int | None = None
    previous_cell_id: str | None = None
    last_handover_tick: int | None = None
    interruption_until_tick: int = 0
    handover_count: int = 0
    ping_pong_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "serving_cell_id": self.serving_cell_id,
            "pending_cell_id": self.pending_cell_id,
            "pending_since_tick": self.pending_since_tick,
            "previous_cell_id": self.previous_cell_id,
            "last_handover_tick": self.last_handover_tick,
            "interruption_until_tick": self.interruption_until_tick,
            "handover_count": self.handover_count,
            "ping_pong_count": self.ping_pong_count,
        }


@dataclass(frozen=True, slots=True)
class HandoverTransition:
    tick: int
    ue_id: str
    kind: str
    source_cell_id: str
    target_cell_id: str | None
    measurement_delta_db: float | None
    interruption_until_tick: int
    ping_pong: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "tick": self.tick,
            "ue_id": self.ue_id,
            "kind": self.kind,
            "source_cell_id": self.source_cell_id,
            "target_cell_id": self.target_cell_id,
            "measurement_delta_db": self.measurement_delta_db,
            "interruption_until_tick": self.interruption_until_tick,
            "ping_pong": self.ping_pong,
        }


@dataclass(frozen=True, slots=True)
class AvailabilityState:
    outage: bool = False
    outage_pending_since_tick: int | None = None
    recovery_pending_since_tick: int | None = None
    outage_transition_count: int = 0
    recovery_transition_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "outage": self.outage,
            "outage_pending_since_tick": self.outage_pending_since_tick,
            "recovery_pending_since_tick": self.recovery_pending_since_tick,
            "outage_transition_count": self.outage_transition_count,
            "recovery_transition_count": self.recovery_transition_count,
        }


@dataclass(frozen=True, slots=True)
class AvailabilityTransition:
    tick: int
    ue_id: str
    kind: str
    sinr_db: float

    def as_dict(self) -> dict[str, object]:
        return {"tick": self.tick, "ue_id": self.ue_id, "kind": self.kind, "sinr_db": self.sinr_db}


def advance_linear_reflect(
    state: MotionState,
    bounds: NormalizedMotionBounds,
    elapsed_ns: int,
) -> MotionState:
    """Advance one UE and reflect its velocity at rectangular boundaries."""

    if elapsed_ns < 0:
        raise ModelDomainError(
            "mobility elapsed time must be nonnegative",
            {"elapsed_ns": elapsed_ns, "requirement": "DYN-MOB-001"},
        )
    seconds = elapsed_ns / 1_000_000_000
    x, vx = _reflect_axis(
        state.position.x_m,
        state.velocity.x_mps,
        float(bounds.x_min_m),
        float(bounds.x_max_m),
        seconds,
    )
    y, vy = _reflect_axis(
        state.position.y_m,
        state.velocity.y_mps,
        float(bounds.y_min_m),
        float(bounds.y_max_m),
        seconds,
    )
    return MotionState(
        position=Position3D(x, y, state.position.z_m),
        velocity=Velocity3D(vx, vy, 0.0),
    )


def evolve_correlated_shadow(
    previous_db: float,
    *,
    sigma_db: float,
    travelled_distance_m: float,
    correlation_distance_m: float,
    innovation_standard_normal: float,
) -> ShadowEvolution:
    """Apply the declared distance-domain first-order Gauss-Markov update."""

    values = (
        previous_db,
        sigma_db,
        travelled_distance_m,
        correlation_distance_m,
        innovation_standard_normal,
    )
    if not all(math.isfinite(value) for value in values):
        raise ModelDomainError(
            "shadow evolution inputs must be finite", {"requirement": "DYN-CH-002"}
        )
    if sigma_db < 0 or travelled_distance_m < 0 or correlation_distance_m <= 0:
        raise ModelDomainError(
            "shadow sigma/distance domain is invalid",
            {"requirement": "DYN-CH-002"},
        )
    rho = math.exp(-travelled_distance_m / correlation_distance_m)
    value = (
        rho * previous_db
        + math.sqrt(max(0.0, 1.0 - rho * rho)) * sigma_db * innovation_standard_normal
    )
    return ShadowEvolution(value, rho, innovation_standard_normal, travelled_distance_m)


def select_horizontal_beam(
    cell_position: Position3D,
    ue_position: Position3D,
    beams: tuple[NormalizedBeam, ...],
) -> BeamSelection:
    """Select the highest-gain configured horizontal beam with lexical ties."""

    if not beams:
        raise ModelDomainError("beam codebook cannot be empty", {"requirement": "DYN-FR2-003"})
    azimuth = (
        math.degrees(
            math.atan2(ue_position.y_m - cell_position.y_m, ue_position.x_m - cell_position.x_m)
        )
        % 360.0
    )
    evaluated = []
    for beam in beams:
        offset = _wrapped_angle_deg(azimuth - float(beam.boresight_azimuth_deg))
        peak = float(beam.peak_gain_db)
        gain = max(
            float(beam.sidelobe_gain_db),
            peak - 12.0 * (offset / float(beam.half_power_beamwidth_deg)) ** 2,
        )
        evaluated.append((gain, beam.beam_id, offset))
    gain, beam_id, offset = sorted(evaluated, key=lambda item: (-item[0], item[1]))[0]
    return BeamSelection(BEAM_PROFILE_ID, beam_id, azimuth, offset, gain)


def explicit_blockage_state(
    *,
    tick: int,
    ue_id: str,
    cell_id: str,
    intervals: tuple[NormalizedBlockageInterval, ...],
) -> BlockageState:
    """Return the largest active configured `[start,end)` excess loss."""

    losses = [
        float(item.excess_loss_db)
        for item in intervals
        if item.ue_id == ue_id and item.cell_id == cell_id and item.start_ns <= tick < item.end_ns
    ]
    loss = max(losses, default=0.0)
    return BlockageState(BLOCKAGE_PROFILE_ID, bool(losses), loss)


def calculate_activity_coupled_sinr(
    serving: LinkBudgetResult,
    links: tuple[LinkBudgetResult, ...],
    *,
    allocated_prbs: int,
    available_prbs: int,
    previous_active_prbs: dict[str, int],
    receiver_noise_figure_db: float,
) -> ActivitySinrResult:
    """Scale flat received PSD by exact low-index PRB overlap and sum in watts."""

    if not 0 < allocated_prbs <= available_prbs:
        raise ModelDomainError(
            "activity-coupled SINR requires a positive allocation within cell capacity",
            {
                "allocated_prbs": allocated_prbs,
                "available_prbs": available_prbs,
                "requirement": "DYN-INT-002",
            },
        )
    prb_bandwidth = 12 * serving.subcarrier_spacing_hz
    evaluated_bandwidth = allocated_prbs * prb_bandwidth
    signal_w = serving.received_psd_w_per_hz * evaluated_bandwidth
    noise_dbm = -174.0 + 10.0 * math.log10(evaluated_bandwidth) + receiver_noise_figure_db
    noise_w = dbm_to_watt(noise_dbm)
    components: list[ActivityInterferenceComponent] = []
    for link in sorted(links, key=lambda item: item.cell_id):
        if link.cell_id == serving.cell_id:
            continue
        active = previous_active_prbs.get(link.cell_id, 0)
        if not 0 <= active <= available_prbs:
            raise ModelDomainError(
                "neighbour active PRBs are outside cell capacity",
                {"cell_id": link.cell_id, "active_prbs": active, "requirement": "DYN-INT-002"},
            )
        overlap = min(allocated_prbs, active)
        power = link.received_psd_w_per_hz * overlap * prb_bandwidth
        components.append(
            ActivityInterferenceComponent(
                cell_id=link.cell_id,
                active_prbs=active,
                overlap_prbs=overlap,
                power_w=power,
                power_dbm=None if power == 0 else watt_to_dbm(power),
            )
        )
    interference_w = math.fsum(item.power_w for item in components)
    denominator = noise_w + interference_w
    ratio = signal_w / denominator
    return ActivitySinrResult(
        profile_id=ACTIVITY_INTERFERENCE_PROFILE_ID,
        allocated_prbs=allocated_prbs,
        prb_bandwidth_hz=prb_bandwidth,
        signal_power_w=signal_w,
        noise_power_w=noise_w,
        interference_power_w=interference_w,
        sinr_linear=ratio,
        sinr_db=10.0 * math.log10(ratio),
        components=tuple(components),
    )


def update_handover_state(
    state: HandoverState,
    *,
    tick: int,
    ue_id: str,
    measurements_dbm: dict[str, float],
    config: NormalizedHandover,
) -> tuple[HandoverState, HandoverTransition | None]:
    """Advance the declared A3-inspired continuous-entry state machine."""

    if state.serving_cell_id not in measurements_dbm:
        raise ModelDomainError(
            "serving cell is absent from measurements",
            {"ue_id": ue_id, "requirement": "DYN-HO-001"},
        )
    neighbours = sorted(
        (
            (value, cell_id)
            for cell_id, value in measurements_dbm.items()
            if cell_id != state.serving_cell_id
        ),
        key=lambda item: (-item[0], item[1]),
    )
    if not neighbours:
        return state, None
    neighbour_value, neighbour_id = neighbours[0]
    delta = neighbour_value - measurements_dbm[state.serving_cell_id]
    enter = float(config.offset_db + config.hysteresis_db)
    leave = float(config.offset_db - config.hysteresis_db)
    pending_id = state.pending_cell_id
    pending_since = state.pending_since_tick
    transition: HandoverTransition | None = None
    if delta > enter:
        if pending_id != neighbour_id:
            pending_id = neighbour_id
            pending_since = tick
            transition = HandoverTransition(
                tick,
                ue_id,
                "a3_entered",
                state.serving_cell_id,
                neighbour_id,
                delta,
                state.interruption_until_tick,
            )
        if pending_since is not None and tick - pending_since >= config.time_to_trigger_ns:
            ping_pong = (
                state.previous_cell_id == neighbour_id
                and state.last_handover_tick is not None
                and tick - state.last_handover_tick <= config.ping_pong_window_ns
            )
            updated = HandoverState(
                serving_cell_id=neighbour_id,
                previous_cell_id=state.serving_cell_id,
                last_handover_tick=tick,
                interruption_until_tick=tick + config.interruption_ns,
                handover_count=state.handover_count + 1,
                ping_pong_count=state.ping_pong_count + int(ping_pong),
            )
            return updated, HandoverTransition(
                tick,
                ue_id,
                "handover_executed",
                state.serving_cell_id,
                neighbour_id,
                delta,
                updated.interruption_until_tick,
                ping_pong,
            )
    elif pending_id is not None and delta < leave:
        transition = HandoverTransition(
            tick,
            ue_id,
            "a3_cancelled",
            state.serving_cell_id,
            pending_id,
            delta,
            state.interruption_until_tick,
        )
        pending_id = None
        pending_since = None
    return (
        HandoverState(
            serving_cell_id=state.serving_cell_id,
            pending_cell_id=pending_id,
            pending_since_tick=pending_since,
            previous_cell_id=state.previous_cell_id,
            last_handover_tick=state.last_handover_tick,
            interruption_until_tick=state.interruption_until_tick,
            handover_count=state.handover_count,
            ping_pong_count=state.ping_pong_count,
        ),
        transition,
    )


def update_availability_state(
    state: AvailabilityState,
    *,
    tick: int,
    ue_id: str,
    sinr_db: float,
    config: NormalizedAvailability,
) -> tuple[AvailabilityState, AvailabilityTransition | None]:
    """Advance project-defined scheduling availability with hysteresis and dwell times."""

    if not math.isfinite(sinr_db):
        raise ModelDomainError(
            "availability SINR must be finite", {"ue_id": ue_id, "requirement": "DYN-AVL-001"}
        )
    if not state.outage:
        since = state.outage_pending_since_tick
        if sinr_db <= float(config.outage_threshold_db):
            since = tick if since is None else since
            if tick - since >= config.outage_time_to_trigger_ns:
                updated = AvailabilityState(
                    outage=True,
                    outage_transition_count=state.outage_transition_count + 1,
                    recovery_transition_count=state.recovery_transition_count,
                )
                return updated, AvailabilityTransition(tick, ue_id, "outage_entered", sinr_db)
        else:
            since = None
        return (
            AvailabilityState(
                outage=False,
                outage_pending_since_tick=since,
                outage_transition_count=state.outage_transition_count,
                recovery_transition_count=state.recovery_transition_count,
            ),
            None,
        )
    since = state.recovery_pending_since_tick
    if sinr_db >= float(config.recovery_threshold_db):
        since = tick if since is None else since
        if tick - since >= config.recovery_time_to_trigger_ns:
            updated = AvailabilityState(
                outage=False,
                outage_transition_count=state.outage_transition_count,
                recovery_transition_count=state.recovery_transition_count + 1,
            )
            return updated, AvailabilityTransition(tick, ue_id, "outage_recovered", sinr_db)
    else:
        since = None
    return (
        AvailabilityState(
            outage=True,
            recovery_pending_since_tick=since,
            outage_transition_count=state.outage_transition_count,
            recovery_transition_count=state.recovery_transition_count,
        ),
        None,
    )


def _reflect_axis(
    position: float, velocity: float, lower: float, upper: float, seconds: float
) -> tuple[float, float]:
    if not lower <= position <= upper or lower >= upper:
        raise ModelDomainError(
            "mobility position/bounds are invalid",
            {"position": position, "lower": lower, "upper": upper, "requirement": "DYN-MOB-001"},
        )
    if velocity == 0.0 or seconds == 0.0:
        return position, velocity
    length = upper - lower
    unwrapped = position - lower + velocity * seconds
    segment = math.floor(unwrapped / length)
    remainder = unwrapped - segment * length
    if math.isclose(remainder, 0.0, abs_tol=1e-12) and velocity < 0:
        segment -= 1
        remainder = length
    if segment % 2 == 0:
        return lower + remainder, velocity
    return upper - remainder, -velocity


def _wrapped_angle_deg(value: float) -> float:
    return abs((value + 180.0) % 360.0 - 180.0)
