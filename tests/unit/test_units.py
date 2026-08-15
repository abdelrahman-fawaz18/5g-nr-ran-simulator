from decimal import Decimal

import pytest

from nr_ran_sim.config.units import QuantityKind, convert_value, require_integral
from nr_ran_sim.errors import ConfigurationValidationError


@pytest.mark.parametrize(
    ("value", "unit", "kind", "expected"),
    [
        ("1.25", "ms", QuantityKind.TIME, Decimal("1250000")),
        ("3.5", "GHz", QuantityKind.FREQUENCY, Decimal("3500000000")),
        ("1.5", "km", QuantityKind.DISTANCE, Decimal("1500")),
        ("2", "mW", QuantityKind.POWER, Decimal("0.002")),
        ("3", "dB", QuantityKind.LOSS, Decimal("3")),
        ("4", "dBi", QuantityKind.GAIN, Decimal("4")),
        ("12", "kbit", QuantityKind.DATA, Decimal("12000")),
        ("2", "Mbit/s", QuantityKind.RATE, Decimal("2000000")),
    ],
)
def test_quantity_conversion(
    value: str,
    unit: str,
    kind: QuantityKind,
    expected: Decimal,
) -> None:
    assert convert_value(Decimal(value), unit, kind, "field") == expected


def test_dbm_conversion_is_decimal_domain() -> None:
    watts = convert_value(Decimal("46"), "dBm", QuantityKind.POWER, "power")
    assert abs(watts - Decimal("39.810717055349725")) < Decimal("1e-15")


@pytest.mark.parametrize(
    ("value", "unit", "kind"),
    [
        (Decimal("NaN"), "ms", QuantityKind.TIME),
        (Decimal("1"), "meters", QuantityKind.TIME),
        (Decimal("1"), "dB", QuantityKind.POWER),
    ],
)
def test_invalid_quantities_fail_with_context(
    value: Decimal,
    unit: str,
    kind: QuantityKind,
) -> None:
    with pytest.raises(ConfigurationValidationError) as raised:
        convert_value(value, unit, kind, "radio.field")
    assert raised.value.context["field"] == "radio.field"
    assert raised.value.code == "configuration_validation_error"


def test_integral_conversion_rejects_fractional_canonical_value() -> None:
    with pytest.raises(ConfigurationValidationError, match="integer number"):
        require_integral(Decimal("1.5"), "simulation.time", "ns")
    assert require_integral(Decimal("42"), "field", "bit") == 42
