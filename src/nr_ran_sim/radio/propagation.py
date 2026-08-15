"""TR 38.901 V18.1.0 outdoor path-loss, LOS, and static shadow models."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal, NoReturn

from nr_ran_sim.errors import ModelDomainError
from nr_ran_sim.experiments.seeds import OwnedRng
from nr_ran_sim.radio.geometry import LinkGeometry

Scenario = Literal["rma", "uma", "umi_street_canyon"]
PropagationState = Literal["los", "nlos"]
DomainStatus = Literal["inside"]

MODEL_ID = "3gpp-tr38901-r18-v18.1.0"
SOURCE_LOCATION = "TR 38.901 V18.1.0 Table 7.4.1-1"
LOS_SOURCE_LOCATION = "TR 38.901 V18.1.0 Table 7.4.2-1"
SPEED_OF_LIGHT_MPS = 3.0e8
MINIMUM_CARRIER_HZ = 0.5e9
TIER_A_MAXIMUM_CARRIER_HZ = 7.125e9
TR38901_MAXIMUM_CARRIER_HZ = 100.0e9


@dataclass(frozen=True, slots=True)
class LosSelectionResult:
    mode: str
    state: PropagationState
    probability_los: float
    uniform_draw: float | None
    source_location: str = LOS_SOURCE_LOCATION

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "state": self.state,
            "probability_los": self.probability_los,
            "uniform_draw": self.uniform_draw,
            "source_location": self.source_location,
        }


@dataclass(frozen=True, slots=True)
class PathLossResult:
    model_id: str
    source_location: str
    scenario: Scenario
    state: PropagationState
    domain_status: DomainStatus
    carrier_frequency_hz: float
    horizontal_distance_m: float
    direct_distance_m: float
    base_station_height_m: float
    user_terminal_height_m: float
    effective_environment_height_m: float | None
    average_building_height_m: float | None
    average_street_width_m: float | None
    breakpoint_distance_m: float
    los_segment: str
    los_path_loss_db: float
    nlos_candidate_path_loss_db: float | None
    basic_path_loss_db: float
    shadow_standard_deviation_db: float
    shadow_fading_db: float
    total_path_loss_db: float

    def with_shadow(self, shadow_fading_db: float) -> PathLossResult:
        if not math.isfinite(shadow_fading_db):
            raise ModelDomainError(
                "shadow-fading value must be finite",
                {"shadow_fading_db": shadow_fading_db, "requirement": "PROP-007"},
            )
        return replace(
            self,
            shadow_fading_db=shadow_fading_db,
            total_path_loss_db=self.basic_path_loss_db + shadow_fading_db,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "source_location": self.source_location,
            "scenario": self.scenario,
            "state": self.state,
            "domain_status": self.domain_status,
            "carrier_frequency_hz": self.carrier_frequency_hz,
            "horizontal_distance_m": self.horizontal_distance_m,
            "direct_distance_m": self.direct_distance_m,
            "base_station_height_m": self.base_station_height_m,
            "user_terminal_height_m": self.user_terminal_height_m,
            "effective_environment_height_m": self.effective_environment_height_m,
            "average_building_height_m": self.average_building_height_m,
            "average_street_width_m": self.average_street_width_m,
            "breakpoint_distance_m": self.breakpoint_distance_m,
            "los_segment": self.los_segment,
            "los_path_loss_db": self.los_path_loss_db,
            "nlos_candidate_path_loss_db": self.nlos_candidate_path_loss_db,
            "basic_path_loss_db": self.basic_path_loss_db,
            "shadow_standard_deviation_db": self.shadow_standard_deviation_db,
            "shadow_fading_db": self.shadow_fading_db,
            "total_path_loss_db": self.total_path_loss_db,
        }


def los_probability(
    scenario: Scenario,
    horizontal_distance_m: float,
    user_terminal_height_m: float,
) -> float:
    """Evaluate the scenario row in TR 38.901 Table 7.4.2-1."""

    _positive_finite("horizontal_distance_m", horizontal_distance_m, "PROP-006")
    if scenario == "rma":
        probability = (
            1.0
            if horizontal_distance_m <= 10.0
            else math.exp(-(horizontal_distance_m - 10.0) / 1000.0)
        )
    elif scenario == "umi_street_canyon":
        probability = _urban_los_probability(horizontal_distance_m, 36.0)
    elif scenario == "uma":
        base = _urban_los_probability(horizontal_distance_m, 63.0)
        height_correction = (
            0.0
            if user_terminal_height_m <= 13.0
            else ((user_terminal_height_m - 13.0) / 10.0) ** 1.5
        )
        distance_correction = (
            1.25 * (horizontal_distance_m / 100.0) ** 3 * math.exp(-horizontal_distance_m / 150.0)
        )
        probability = base * (1.0 + height_correction * distance_correction)
    else:  # pragma: no cover - closed by typed configuration
        raise ModelDomainError(
            "unsupported path-loss scenario",
            {"scenario": scenario, "requirement": "PROP-003"},
        )
    if not 0.0 <= probability <= 1.0:
        raise ModelDomainError(
            "LOS probability formula produced a value outside [0,1]",
            {
                "scenario": scenario,
                "horizontal_distance_m": horizontal_distance_m,
                "probability": probability,
                "requirement": "PROP-006",
            },
        )
    return probability


def select_los_state(
    scenario: Scenario,
    horizontal_distance_m: float,
    user_terminal_height_m: float,
    *,
    mode: Literal["explicit", "probability_static"],
    explicit_state: PropagationState | None,
    rng: OwnedRng | None,
) -> LosSelectionResult:
    probability = los_probability(scenario, horizontal_distance_m, user_terminal_height_m)
    if mode == "explicit":
        if explicit_state is None:
            raise ModelDomainError(
                "explicit LOS mode requires a supplied per-link state",
                {"requirement": "PROP-006"},
            )
        return LosSelectionResult(
            mode=mode,
            state=explicit_state,
            probability_los=probability,
            uniform_draw=None,
        )
    if rng is None:
        raise ModelDomainError(
            "probability_static LOS mode requires an owned RNG stream",
            {"requirement": "PROP-006"},
        )
    draw = rng.standard_uniform()
    return LosSelectionResult(
        mode=mode,
        state="los" if draw < probability else "nlos",
        probability_los=probability,
        uniform_draw=draw,
    )


def select_effective_environment_height_m(
    scenario: Scenario,
    horizontal_distance_m: float,
    user_terminal_height_m: float,
    *,
    rng: OwnedRng | None,
) -> float | None:
    """Return Note 1 breakpoint environment height; RMa has no such term."""

    if scenario == "rma":
        return None
    if scenario == "umi_street_canyon" or user_terminal_height_m <= 13.0:
        return 1.0
    g = (
        0.0
        if horizontal_distance_m <= 18.0
        else 1.25 * (horizontal_distance_m / 100.0) ** 3 * math.exp(-horizontal_distance_m / 150.0)
    )
    c_value = ((user_terminal_height_m - 13.0) / 10.0) ** 1.5 * g
    probability_one_metre = 1.0 / (1.0 + c_value)
    if probability_one_metre >= 1.0:
        return 1.0
    if rng is None:
        raise ModelDomainError(
            "UMa effective environment height requires an owned RNG stream",
            {"requirement": "PROP-003", "standard_trace": "STD-PL-002"},
        )
    if rng.standard_uniform() < probability_one_metre:
        return 1.0
    maximum_candidate = user_terminal_height_m - 1.5
    candidates = [value for value in range(12, 24, 3) if value <= maximum_candidate]
    if not candidates:
        raise ModelDomainError(
            "UMa effective environment-height candidate set is empty",
            {
                "user_terminal_height_m": user_terminal_height_m,
                "requirement": "PROP-003",
            },
        )
    index = rng.integer_inclusive(0, len(candidates) - 1)
    return float(candidates[index])


def evaluate_path_loss(
    scenario: Scenario,
    state: PropagationState,
    geometry: LinkGeometry,
    carrier_frequency_hz: float,
    *,
    effective_environment_height_m: float | None,
    average_building_height_m: float | None,
    average_street_width_m: float | None,
    maximum_carrier_hz: float = TIER_A_MAXIMUM_CARRIER_HZ,
) -> PathLossResult:
    """Evaluate one supported Table 7.4.1-1 row without clipping/extrapolation."""

    h_bs = geometry.transmitter.z_m
    h_ut = geometry.receiver.z_m
    d_2d = geometry.horizontal_distance_m
    d_3d = geometry.direct_distance_m
    _validate_common_domain(
        scenario,
        state,
        d_2d,
        d_3d,
        h_bs,
        h_ut,
        carrier_frequency_hz,
        maximum_carrier_hz,
    )
    frequency_ghz = carrier_frequency_hz / 1.0e9
    if scenario == "rma":
        result = _rma_path_loss(
            state,
            d_2d,
            d_3d,
            h_bs,
            h_ut,
            frequency_ghz,
            carrier_frequency_hz,
            average_building_height_m,
            average_street_width_m,
        )
    elif scenario == "uma":
        result = _uma_path_loss(
            state,
            d_2d,
            d_3d,
            h_bs,
            h_ut,
            frequency_ghz,
            carrier_frequency_hz,
            effective_environment_height_m,
        )
    else:
        result = _umi_path_loss(
            state,
            d_2d,
            d_3d,
            h_bs,
            h_ut,
            frequency_ghz,
            carrier_frequency_hz,
            effective_environment_height_m,
        )
    (
        breakpoint,
        segment,
        los_loss,
        nlos_candidate,
        basic_loss,
        sigma,
    ) = result
    return PathLossResult(
        model_id=MODEL_ID,
        source_location=SOURCE_LOCATION,
        scenario=scenario,
        state=state,
        domain_status="inside",
        carrier_frequency_hz=carrier_frequency_hz,
        horizontal_distance_m=d_2d,
        direct_distance_m=d_3d,
        base_station_height_m=h_bs,
        user_terminal_height_m=h_ut,
        effective_environment_height_m=effective_environment_height_m,
        average_building_height_m=average_building_height_m,
        average_street_width_m=average_street_width_m,
        breakpoint_distance_m=breakpoint,
        los_segment=segment,
        los_path_loss_db=los_loss,
        nlos_candidate_path_loss_db=nlos_candidate,
        basic_path_loss_db=basic_loss,
        shadow_standard_deviation_db=sigma,
        shadow_fading_db=0.0,
        total_path_loss_db=basic_loss,
    )


def draw_static_shadow_fading_db(path_loss: PathLossResult, rng: OwnedRng | None) -> float:
    if rng is None:
        return 0.0
    return rng.normal(0.0, path_loss.shadow_standard_deviation_db)


def _urban_los_probability(distance_m: float, decay_m: float) -> float:
    if distance_m <= 18.0:
        return 1.0
    return 18.0 / distance_m + math.exp(-distance_m / decay_m) * (1.0 - 18.0 / distance_m)


def _validate_common_domain(
    scenario: Scenario,
    state: PropagationState,
    d_2d: float,
    d_3d: float,
    h_bs: float,
    h_ut: float,
    carrier_hz: float,
    maximum_carrier_hz: float,
) -> None:
    for field, value in (
        ("horizontal_distance_m", d_2d),
        ("direct_distance_m", d_3d),
        ("base_station_height_m", h_bs),
        ("user_terminal_height_m", h_ut),
        ("carrier_frequency_hz", carrier_hz),
    ):
        _positive_finite(field, value, "PROP-004")
    _positive_finite("maximum_carrier_hz", maximum_carrier_hz, "PROP-004")
    if not MINIMUM_CARRIER_HZ <= carrier_hz <= maximum_carrier_hz:
        _domain_error(
            scenario,
            state,
            "carrier_frequency_hz",
            carrier_hz,
            f"{MINIMUM_CARRIER_HZ}-{maximum_carrier_hz}",
        )
    maximum_distance = 5000.0 if scenario != "rma" or state == "nlos" else 10000.0
    if not 10.0 <= d_2d <= maximum_distance:
        _domain_error(scenario, state, "horizontal_distance_m", d_2d, f"10-{maximum_distance}")
    if scenario == "rma":
        if not 10.0 <= h_bs <= 150.0:
            _domain_error(scenario, state, "base_station_height_m", h_bs, "10-150")
        if not 1.0 <= h_ut <= 10.0:
            _domain_error(scenario, state, "user_terminal_height_m", h_ut, "1-10")
    elif scenario == "uma":
        if h_bs != 25.0:
            _domain_error(scenario, state, "base_station_height_m", h_bs, "25")
        if not 1.5 <= h_ut <= 22.5:
            _domain_error(scenario, state, "user_terminal_height_m", h_ut, "1.5-22.5")
    else:
        if h_bs != 10.0:
            _domain_error(scenario, state, "base_station_height_m", h_bs, "10")
        if not 1.5 <= h_ut <= 22.5:
            _domain_error(scenario, state, "user_terminal_height_m", h_ut, "1.5-22.5")


def _rma_path_loss(
    state: PropagationState,
    d_2d: float,
    d_3d: float,
    h_bs: float,
    h_ut: float,
    frequency_ghz: float,
    carrier_hz: float,
    average_building_height_m: float | None,
    average_street_width_m: float | None,
) -> tuple[float, str, float, float | None, float, float]:
    if average_building_height_m is None or average_street_width_m is None:
        raise ModelDomainError(
            "RMa requires average building height and street width",
            {"requirement": "PROP-004", "standard_trace": "STD-PL-001"},
        )
    if not 5.0 <= average_building_height_m <= 50.0:
        _domain_error("rma", state, "average_building_height_m", average_building_height_m, "5-50")
    if not 5.0 <= average_street_width_m <= 50.0:
        _domain_error("rma", state, "average_street_width_m", average_street_width_m, "5-50")
    breakpoint = 2.0 * math.pi * h_bs * h_ut * carrier_hz / SPEED_OF_LIGHT_MPS
    los_first = _rma_los_first(d_3d, frequency_ghz, average_building_height_m)
    if d_2d <= breakpoint:
        los_loss = los_first
        segment = "pl1"
    else:
        los_at_breakpoint = _rma_los_first(
            breakpoint,
            frequency_ghz,
            average_building_height_m,
        )
        los_loss = los_at_breakpoint + 40.0 * math.log10(d_3d / breakpoint)
        segment = "pl2"
    if state == "los":
        sigma = 4.0 if segment == "pl1" else 6.0
        return breakpoint, segment, los_loss, None, los_loss, sigma
    h = average_building_height_m
    w = average_street_width_m
    candidate = (
        161.04
        - 7.1 * math.log10(w)
        + 7.5 * math.log10(h)
        - (24.37 - 3.7 * (h / h_bs) ** 2) * math.log10(h_bs)
        + (43.42 - 3.1 * math.log10(h_bs)) * (math.log10(d_3d) - 3.0)
        + 20.0 * math.log10(frequency_ghz)
        - (3.2 * math.log10(11.75 * h_ut) ** 2 - 4.97)
    )
    return breakpoint, segment, los_loss, candidate, max(los_loss, candidate), 8.0


def _rma_los_first(direct_distance_m: float, frequency_ghz: float, h_m: float) -> float:
    return float(
        20.0 * math.log10(40.0 * math.pi * direct_distance_m * frequency_ghz / 3.0)
        + min(0.03 * h_m**1.72, 10.0) * math.log10(direct_distance_m)
        - min(0.044 * h_m**1.72, 14.77)
        + 0.002 * math.log10(h_m) * direct_distance_m
    )


def _uma_path_loss(
    state: PropagationState,
    d_2d: float,
    d_3d: float,
    h_bs: float,
    h_ut: float,
    frequency_ghz: float,
    carrier_hz: float,
    effective_environment_height_m: float | None,
) -> tuple[float, str, float, float | None, float, float]:
    effective = _validate_effective_environment_height(
        "uma", state, effective_environment_height_m, h_bs, h_ut
    )
    breakpoint = 4.0 * (h_bs - effective) * (h_ut - effective) * carrier_hz / SPEED_OF_LIGHT_MPS
    pl1 = 28.0 + 22.0 * math.log10(d_3d) + 20.0 * math.log10(frequency_ghz)
    if d_2d <= breakpoint:
        los_loss = pl1
        segment = "pl1"
    else:
        los_loss = (
            28.0
            + 40.0 * math.log10(d_3d)
            + 20.0 * math.log10(frequency_ghz)
            - 9.0 * math.log10(breakpoint**2 + (h_bs - h_ut) ** 2)
        )
        segment = "pl2"
    if state == "los":
        return breakpoint, segment, los_loss, None, los_loss, 4.0
    candidate = (
        13.54 + 39.08 * math.log10(d_3d) + 20.0 * math.log10(frequency_ghz) - 0.6 * (h_ut - 1.5)
    )
    return breakpoint, segment, los_loss, candidate, max(los_loss, candidate), 6.0


def _umi_path_loss(
    state: PropagationState,
    d_2d: float,
    d_3d: float,
    h_bs: float,
    h_ut: float,
    frequency_ghz: float,
    carrier_hz: float,
    effective_environment_height_m: float | None,
) -> tuple[float, str, float, float | None, float, float]:
    effective = _validate_effective_environment_height(
        "umi_street_canyon", state, effective_environment_height_m, h_bs, h_ut
    )
    if effective != 1.0:
        _domain_error("umi_street_canyon", state, "effective_environment_height_m", effective, "1")
    breakpoint = 4.0 * (h_bs - effective) * (h_ut - effective) * carrier_hz / SPEED_OF_LIGHT_MPS
    pl1 = 32.4 + 21.0 * math.log10(d_3d) + 20.0 * math.log10(frequency_ghz)
    if d_2d <= breakpoint:
        los_loss = pl1
        segment = "pl1"
    else:
        los_loss = (
            32.4
            + 40.0 * math.log10(d_3d)
            + 20.0 * math.log10(frequency_ghz)
            - 9.5 * math.log10(breakpoint**2 + (h_bs - h_ut) ** 2)
        )
        segment = "pl2"
    if state == "los":
        return breakpoint, segment, los_loss, None, los_loss, 4.0
    candidate = (
        22.4 + 35.3 * math.log10(d_3d) + 21.3 * math.log10(frequency_ghz) - 0.3 * (h_ut - 1.5)
    )
    return breakpoint, segment, los_loss, candidate, max(los_loss, candidate), 7.82


def _validate_effective_environment_height(
    scenario: Scenario,
    state: PropagationState,
    value: float | None,
    h_bs: float,
    h_ut: float,
) -> float:
    if value is None or not math.isfinite(value) or not 0.0 < value < min(h_bs, h_ut):
        _domain_error(
            scenario,
            state,
            "effective_environment_height_m",
            value,
            f">0 and <{min(h_bs, h_ut)}",
        )
    return value


def _positive_finite(field: str, value: float, requirement: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ModelDomainError(
            f"{field} must be finite and positive",
            {"field": field, "value": value, "requirement": requirement},
        )


def _domain_error(
    scenario: Scenario,
    state: PropagationState,
    field: str,
    value: object,
    expected: str,
) -> NoReturn:
    standard_trace = {
        "rma": "STD-PL-001",
        "uma": "STD-PL-002",
        "umi_street_canyon": "STD-PL-003",
    }[scenario]
    raise ModelDomainError(
        "path-loss input is outside the supported model domain",
        {
            "scenario": scenario,
            "state": state,
            "field": field,
            "value": value,
            "expected": expected,
            "requirement": "PROP-004",
            "standard_trace": standard_trace,
        },
    )
