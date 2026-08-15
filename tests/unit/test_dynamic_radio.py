"""Hand-checkable vectors for the opt-in dynamic-radio models."""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from nr_ran_sim.config.dynamic import (
    NormalizedAvailability,
    NormalizedBeam,
    NormalizedBlockageInterval,
    NormalizedHandover,
    NormalizedMotionBounds,
)
from nr_ran_sim.radio.dynamic import (
    AvailabilityState,
    HandoverState,
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
from nr_ran_sim.radio.geometry import Position3D
from nr_ran_sim.radio.link import LinkBudgetResult


def _bounds() -> NormalizedMotionBounds:
    return NormalizedMotionBounds(
        x_min_m=Decimal("0"),
        x_max_m=Decimal("10"),
        y_min_m=Decimal("0"),
        y_max_m=Decimal("10"),
    )


def _handover(*, ttt: int = 2, interruption: int = 1) -> NormalizedHandover:
    return NormalizedHandover(
        profile="a3-inspired-long-term-rsrp-v1",
        offset_db=Decimal("1"),
        hysteresis_db=Decimal("0.5"),
        time_to_trigger_ns=ttt,
        interruption_ns=interruption,
        ping_pong_window_ns=10,
    )


def _availability() -> NormalizedAvailability:
    return NormalizedAvailability(
        profile="sinr-hysteresis-availability-v1",
        outage_threshold_db=Decimal("-5"),
        recovery_threshold_db=Decimal("-2"),
        outage_time_to_trigger_ns=2,
        recovery_time_to_trigger_ns=2,
    )


def _link(cell_id: str, received_psd_w_per_hz: float) -> LinkBudgetResult:
    return LinkBudgetResult(
        cell_id=cell_id,
        ue_id="ue/users/0000",
        transmission_bandwidth_hz=3_600_000,
        subcarrier_spacing_hz=30_000,
        transmit_power_w=1.0,
        transmit_power_dbm=30.0,
        transmit_psd_w_per_hz=1.0,
        transmit_psd_dbm_per_hz=30.0,
        transmitter_gain_dbi=0.0,
        receiver_gain_dbi=0.0,
        basic_path_loss_db=0.0,
        shadow_fading_db=0.0,
        penetration_loss_db=0.0,
        miscellaneous_loss_db=0.0,
        total_link_loss_db=0.0,
        received_power_w=received_psd_w_per_hz * 3_600_000,
        received_power_dbm=0.0,
        received_psd_w_per_hz=received_psd_w_per_hz,
        received_psd_dbm_per_hz=0.0,
        reference_signal_received_power_w=received_psd_w_per_hz * 30_000,
        reference_signal_received_power_dbm=0.0,
    )


def test_linear_motion_reflects_and_preserves_elapsed_distance() -> None:
    state = MotionState(Position3D(9.0, 1.0, 1.5), Velocity3D(3.0, -2.0))
    advanced = advance_linear_reflect(state, _bounds(), 2_000_000_000)

    assert advanced.position == Position3D(5.0, 3.0, 1.5)
    assert advanced.velocity == Velocity3D(-3.0, 2.0)
    assert advance_linear_reflect(advanced, _bounds(), 0) == advanced

    multiple = advance_linear_reflect(
        MotionState(Position3D(1.0, 5.0, 1.5), Velocity3D(7.0, 0.0)),
        _bounds(),
        5_000_000_000,
    )
    assert multiple.position.x_m == pytest.approx(4.0)
    assert multiple.velocity.x_mps == -7.0


def test_distance_correlated_shadow_matches_declared_equation() -> None:
    unchanged = evolve_correlated_shadow(
        3.0,
        sigma_db=4.0,
        travelled_distance_m=0.0,
        correlation_distance_m=10.0,
        innovation_standard_normal=99.0,
    )
    assert unchanged.rho == 1.0
    assert unchanged.value_db == 3.0

    independent = evolve_correlated_shadow(
        0.0,
        sigma_db=4.0,
        travelled_distance_m=10_000.0,
        correlation_distance_m=1.0,
        innovation_standard_normal=0.5,
    )
    assert independent.rho == pytest.approx(0.0, abs=1e-12)
    assert independent.value_db == pytest.approx(2.0)


def test_shadow_innovations_reproduce_configured_independent_limit_variance() -> None:
    rng = np.random.default_rng(20260814)
    samples = [
        evolve_correlated_shadow(
            0.0,
            sigma_db=4.0,
            travelled_distance_m=10_000.0,
            correlation_distance_m=1.0,
            innovation_standard_normal=float(value),
        ).value_db
        for value in rng.normal(size=20_000)
    ]
    assert float(np.mean(samples)) == pytest.approx(0.0, abs=0.1)
    assert float(np.std(samples)) == pytest.approx(4.0, rel=0.02)


def test_beam_selection_uses_wrapped_angle_and_lexical_tie_break() -> None:
    beams = (
        NormalizedBeam(
            beam_id="beam-b",
            boresight_azimuth_deg=Decimal("10"),
            peak_gain_db=Decimal("12"),
            half_power_beamwidth_deg=Decimal("60"),
            sidelobe_gain_db=Decimal("-5"),
        ),
        NormalizedBeam(
            beam_id="beam-a",
            boresight_azimuth_deg=Decimal("350"),
            peak_gain_db=Decimal("12"),
            half_power_beamwidth_deg=Decimal("60"),
            sidelobe_gain_db=Decimal("-5"),
        ),
    )
    selected = select_horizontal_beam(Position3D(0, 0, 10), Position3D(1, 0, 1.5), beams)
    assert selected.beam_id == "beam-a"
    assert selected.wrapped_offset_deg == pytest.approx(10.0)


def test_blockage_intervals_are_half_open_and_take_maximum_overlap() -> None:
    intervals = (
        NormalizedBlockageInterval(
            ue_id="ue/users/0000",
            cell_id="cell/cell-a",
            start_ns=2,
            end_ns=5,
            excess_loss_db=Decimal("10"),
        ),
        NormalizedBlockageInterval(
            ue_id="ue/users/0000",
            cell_id="cell/cell-a",
            start_ns=3,
            end_ns=4,
            excess_loss_db=Decimal("20"),
        ),
    )
    assert not explicit_blockage_state(
        tick=5, ue_id="ue/users/0000", cell_id="cell/cell-a", intervals=intervals
    ).blocked
    assert (
        explicit_blockage_state(
            tick=3, ue_id="ue/users/0000", cell_id="cell/cell-a", intervals=intervals
        ).excess_loss_db
        == 20.0
    )


def test_activity_interference_uses_exact_low_index_prb_overlap() -> None:
    serving = _link("cell/cell-a", 2e-12)
    neighbour = _link("cell/cell-b", 1e-12)
    result = calculate_activity_coupled_sinr(
        serving,
        (serving, neighbour),
        allocated_prbs=4,
        available_prbs=10,
        previous_active_prbs={"cell/cell-b": 2},
        receiver_noise_figure_db=7.0,
    )

    assert result.components[0].overlap_prbs == 2
    assert result.signal_power_w == pytest.approx(2e-12 * 4 * 360_000)
    assert result.interference_power_w == pytest.approx(1e-12 * 2 * 360_000)

    second_neighbour = _link("cell/cell-c", 2e-12)
    mixed = calculate_activity_coupled_sinr(
        serving,
        (serving, neighbour, second_neighbour),
        allocated_prbs=4,
        available_prbs=10,
        previous_active_prbs={"cell/cell-b": 0, "cell/cell-c": 10},
        receiver_noise_figure_db=7.0,
    )
    assert [item.overlap_prbs for item in mixed.components] == [0, 4]
    assert mixed.interference_power_w == pytest.approx(2e-12 * 4 * 360_000)


def test_handover_threshold_equalities_cancel_rule_and_lexical_tie() -> None:
    config = _handover(ttt=10)
    state = HandoverState("cell/a")
    state, transition = update_handover_state(
        state,
        tick=0,
        ue_id="ue/u/0000",
        measurements_dbm={"cell/a": -80.0, "cell/b": -78.5, "cell/c": -78.5},
        config=config,
    )
    assert transition is None
    assert state.pending_cell_id is None

    state, transition = update_handover_state(
        state,
        tick=1,
        ue_id="ue/u/0000",
        measurements_dbm={"cell/a": -80.0, "cell/b": -78.0, "cell/c": -78.0},
        config=config,
    )
    assert transition is not None
    assert state.pending_cell_id == "cell/b"

    state, transition = update_handover_state(
        state,
        tick=2,
        ue_id="ue/u/0000",
        measurements_dbm={"cell/a": -80.0, "cell/b": -79.5, "cell/c": -90.0},
        config=config,
    )
    assert transition is None
    assert state.pending_cell_id == "cell/b"
    state, transition = update_handover_state(
        state,
        tick=3,
        ue_id="ue/u/0000",
        measurements_dbm={"cell/a": -80.0, "cell/b": -79.6, "cell/c": -90.0},
        config=config,
    )
    assert transition is not None
    assert transition.kind == "a3_cancelled"
    assert state.pending_cell_id is None


def test_handover_requires_continuous_ttt_and_counts_ping_pong() -> None:
    state = HandoverState("cell/a")
    state, entered = update_handover_state(
        state,
        tick=0,
        ue_id="ue/u/0000",
        measurements_dbm={"cell/a": -80.0, "cell/b": -77.0},
        config=_handover(),
    )
    assert entered is not None
    assert entered.kind == "a3_entered"
    state, transition = update_handover_state(
        state,
        tick=2,
        ue_id="ue/u/0000",
        measurements_dbm={"cell/a": -80.0, "cell/b": -77.0},
        config=_handover(),
    )
    assert transition is not None
    assert transition.kind == "handover_executed"
    assert state.serving_cell_id == "cell/b"

    state, _ = update_handover_state(
        state,
        tick=3,
        ue_id="ue/u/0000",
        measurements_dbm={"cell/a": -70.0, "cell/b": -80.0},
        config=_handover(ttt=0),
    )
    assert state.serving_cell_id == "cell/a"
    assert state.ping_pong_count == 1


def test_availability_applies_entry_and_recovery_dwell() -> None:
    state = AvailabilityState()
    state, transition = update_availability_state(
        state, tick=0, ue_id="ue/u/0000", sinr_db=-6.0, config=_availability()
    )
    assert transition is None
    state, transition = update_availability_state(
        state, tick=2, ue_id="ue/u/0000", sinr_db=-6.0, config=_availability()
    )
    assert transition is not None
    assert transition.kind == "outage_entered"
    state, _ = update_availability_state(
        state, tick=3, ue_id="ue/u/0000", sinr_db=-1.0, config=_availability()
    )
    state, transition = update_availability_state(
        state, tick=5, ue_id="ue/u/0000", sinr_db=-1.0, config=_availability()
    )
    assert transition is not None
    assert transition.kind == "outage_recovered"
    assert not state.outage
