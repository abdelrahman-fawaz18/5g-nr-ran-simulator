"""Clarity-first oracle with no imports from production simulator modules."""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any


def evaluate_integrated_link(inputs: dict[str, Any]) -> dict[str, Decimal]:
    """Independently evaluate dB link budgets, thermal noise, interference, and SINR."""

    with localcontext() as context:
        context.prec = 50
        receiver_gain = Decimal(inputs["receiver_gain_dbi"])
        shadow = Decimal(inputs["shadow_fading_db"])
        penetration = Decimal(inputs["penetration_loss_db"])
        miscellaneous = Decimal(inputs["miscellaneous_loss_db"])
        received: list[Decimal] = []
        for link in inputs["links"]:
            received.append(
                Decimal(link["transmit_power_dbm"])
                + Decimal(link["transmitter_gain_dbi"])
                + receiver_gain
                - Decimal(link["basic_path_loss_db"])
                - shadow
                - penetration
                - miscellaneous
            )
        bandwidth_hz = Decimal(inputs["transmission_bandwidth_hz"])
        noise_figure = Decimal(inputs["receiver_noise_figure_db"])
        noise_dbm = Decimal(-174) + Decimal(10) * bandwidth_hz.log10() + noise_figure
        interference_w = sum((_dbm_to_watt(value) for value in received[1:]), Decimal(0))
        interference_dbm = Decimal(10) * interference_w.log10() + Decimal(30)
        sinr_linear = _dbm_to_watt(received[0]) / (_dbm_to_watt(noise_dbm) + interference_w)
        return {
            "serving_received_power_dbm": received[0],
            "noise_power_dbm": noise_dbm,
            "interference_power_w": interference_w,
            "interference_power_dbm": interference_dbm,
            "sinr_linear": sinr_linear,
            "sinr_db": Decimal(10) * sinr_linear.log10(),
        }


def _dbm_to_watt(power_dbm: Decimal) -> Decimal:
    return ((power_dbm - Decimal(30)) * Decimal(10).ln() / Decimal(10)).exp()
