"""Explicit physical-unit parsing and canonical conversion."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Final

import pint

from nr_ran_sim.errors import ConfigurationValidationError

UNIT_REGISTRY: pint.UnitRegistry[Decimal] = pint.UnitRegistry(
    autoconvert_offset_to_baseunit=True,
    non_int_type=Decimal,
)


class QuantityKind(StrEnum):
    TIME = "time"
    FREQUENCY = "frequency"
    DISTANCE = "distance"
    POWER = "power"
    GAIN = "gain"
    LOSS = "loss"
    DATA = "data"
    RATE = "rate"
    SPEED = "speed"
    ANGLE = "angle"


ACCEPTED_UNITS: Final[dict[QuantityKind, frozenset[str]]] = {
    QuantityKind.TIME: frozenset({"ns", "us", "ms", "s"}),
    QuantityKind.FREQUENCY: frozenset({"Hz", "kHz", "MHz", "GHz"}),
    QuantityKind.DISTANCE: frozenset({"mm", "cm", "m", "km"}),
    QuantityKind.POWER: frozenset({"W", "mW", "dBm"}),
    QuantityKind.GAIN: frozenset({"dBi"}),
    QuantityKind.LOSS: frozenset({"dB"}),
    QuantityKind.DATA: frozenset({"bit", "kbit", "Mbit"}),
    QuantityKind.RATE: frozenset({"bit/s", "kbit/s", "Mbit/s"}),
    QuantityKind.SPEED: frozenset({"m/s", "km/h"}),
    QuantityKind.ANGLE: frozenset({"deg", "rad"}),
}

TARGET_UNITS: Final[dict[QuantityKind, str]] = {
    QuantityKind.TIME: "nanosecond",
    QuantityKind.FREQUENCY: "hertz",
    QuantityKind.DISTANCE: "meter",
    QuantityKind.POWER: "watt",
    QuantityKind.DATA: "bit",
    QuantityKind.RATE: "bit / second",
    QuantityKind.SPEED: "meter / second",
    QuantityKind.ANGLE: "degree",
}


def convert_value(value: Decimal, unit: str, kind: QuantityKind, field: str) -> Decimal:
    """Validate an authoring unit and convert its magnitude to the canonical base."""

    if not value.is_finite():
        raise _unit_error(field, value, unit, kind, "magnitude must be finite")
    if unit not in ACCEPTED_UNITS[kind]:
        accepted = sorted(ACCEPTED_UNITS[kind])
        raise _unit_error(field, value, unit, kind, f"accepted units are {accepted}")
    if kind in {QuantityKind.GAIN, QuantityKind.LOSS}:
        return value
    if kind is QuantityKind.POWER and unit == "dBm":
        # Exact Decimal-domain logarithmic conversion avoids binary-float artifacts in manifests.
        return ((value - Decimal(30)) * Decimal(10).ln() / Decimal(10)).exp()
    try:
        converted = UNIT_REGISTRY.Quantity(value, unit).to(TARGET_UNITS[kind]).magnitude
    except (pint.DimensionalityError, pint.UndefinedUnitError) as exc:
        raise _unit_error(field, value, unit, kind, str(exc)) from exc
    return Decimal(str(converted))


def require_integral(value: Decimal, field: str, canonical_unit: str) -> int:
    """Return an integer canonical value or fail rather than round silently."""

    integral = value.to_integral_value()
    if integral != value:
        raise ConfigurationValidationError(
            f"{field} does not resolve to an integer number of {canonical_unit}",
            {"field": field, "canonical_value": str(value), "unit": canonical_unit},
        )
    return int(integral)


def _unit_error(
    field: str,
    value: Decimal,
    unit: str,
    kind: QuantityKind,
    detail: str,
) -> ConfigurationValidationError:
    return ConfigurationValidationError(
        f"invalid {kind.value} quantity at {field}: {detail}",
        {"field": field, "value": str(value), "unit": unit, "kind": kind.value},
    )
