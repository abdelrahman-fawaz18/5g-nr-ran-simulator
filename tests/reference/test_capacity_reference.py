from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
import yaml

from nr_ran_sim.radio.nr_tables import CQI_TABLE_1, MCS_TABLE_1, SMALL_TBS_TABLE
from nr_ran_sim.radio.tbs import determine_transport_block_size

VECTOR_FILE = Path(__file__).parent / "data" / "ts38214_transport_block_vectors.yaml"

CQI_TABLE_1_REFERENCE = (
    (0, None, None, None),
    (1, 2, 78, "0.1523"),
    (2, 2, 120, "0.2344"),
    (3, 2, 193, "0.3770"),
    (4, 2, 308, "0.6016"),
    (5, 2, 449, "0.8770"),
    (6, 2, 602, "1.1758"),
    (7, 4, 378, "1.4766"),
    (8, 4, 490, "1.9141"),
    (9, 4, 616, "2.4063"),
    (10, 6, 466, "2.7305"),
    (11, 6, 567, "3.3223"),
    (12, 6, 666, "3.9023"),
    (13, 6, 772, "4.5234"),
    (14, 6, 873, "5.1152"),
    (15, 6, 948, "5.5547"),
)

MCS_TABLE_1_REFERENCE = (
    (0, 2, 120, "0.2344"),
    (1, 2, 157, "0.3066"),
    (2, 2, 193, "0.3770"),
    (3, 2, 251, "0.4902"),
    (4, 2, 308, "0.6016"),
    (5, 2, 379, "0.7402"),
    (6, 2, 449, "0.8770"),
    (7, 2, 526, "1.0273"),
    (8, 2, 602, "1.1758"),
    (9, 2, 679, "1.3262"),
    (10, 4, 340, "1.3281"),
    (11, 4, 378, "1.4766"),
    (12, 4, 434, "1.6953"),
    (13, 4, 490, "1.9141"),
    (14, 4, 553, "2.1602"),
    (15, 4, 616, "2.4063"),
    (16, 4, 658, "2.5703"),
    (17, 6, 438, "2.5664"),
    (18, 6, 466, "2.7305"),
    (19, 6, 517, "3.0293"),
    (20, 6, 567, "3.3223"),
    (21, 6, 616, "3.6094"),
    (22, 6, 666, "3.9023"),
    (23, 6, 719, "4.2129"),
    (24, 6, 772, "4.5234"),
    (25, 6, 822, "4.8164"),
    (26, 6, 873, "5.1152"),
    (27, 6, 910, "5.3320"),
    (28, 6, 948, "5.5547"),
)

SMALL_TBS_REFERENCE = (
    24,
    32,
    40,
    48,
    56,
    64,
    72,
    80,
    88,
    96,
    104,
    112,
    120,
    128,
    136,
    144,
    152,
    160,
    168,
    176,
    184,
    192,
    208,
    224,
    240,
    256,
    272,
    288,
    304,
    320,
    336,
    352,
    368,
    384,
    408,
    432,
    456,
    480,
    504,
    528,
    552,
    576,
    608,
    640,
    672,
    704,
    736,
    768,
    808,
    848,
    888,
    928,
    984,
    1032,
    1064,
    1128,
    1160,
    1192,
    1224,
    1256,
    1288,
    1320,
    1352,
    1416,
    1480,
    1544,
    1608,
    1672,
    1736,
    1800,
    1864,
    1928,
    2024,
    2088,
    2152,
    2216,
    2280,
    2408,
    2472,
    2536,
    2600,
    2664,
    2728,
    2792,
    2856,
    2976,
    3104,
    3240,
    3368,
    3496,
    3624,
    3752,
    3824,
)


def _floor_log2(value: Fraction) -> int:
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    power = Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)
    return exponent - 1 if power > value else exponent


def _ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def _reference_tbs(vector: dict[str, Any]) -> tuple[str, Fraction, int, int, int]:
    n_info = Fraction(
        vector["allocated_prbs"]
        * vector["data_re_per_prb"]
        * vector["modulation_order"]
        * vector["code_rate_x1024"],
        1024,
    )
    if n_info <= 3824:
        exponent = max(3, _floor_log2(n_info) - 6)
        quantum = 1 << exponent
        quantized = max(24, quantum * int(n_info / quantum))
        tbs = next(value for value in SMALL_TBS_REFERENCE if value >= quantized)
        return "small-table", n_info, quantized, 1, tbs

    shifted = n_info - 24
    exponent = _floor_log2(shifted) - 5
    quantum = 1 << exponent
    quantized = max(3840, quantum * int(shifted / quantum + Fraction(1, 2)))
    if vector["code_rate_x1024"] <= 256:
        blocks = _ceil_div(quantized + 24, 3816)
        branch = "large-low-rate"
    elif quantized > 8424:
        blocks = _ceil_div(quantized + 24, 8424)
        branch = "large-segmented"
    else:
        blocks = 1
        branch = "large"
    tbs = 8 * blocks * _ceil_div(quantized + 24, 8 * blocks) - 24
    return branch, n_info, quantized, blocks, tbs


def _vectors() -> list[dict[str, Any]]:
    payload = yaml.safe_load(VECTOR_FILE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    vectors = payload["vectors"]
    assert isinstance(vectors, list)
    return vectors


def test_release18_cqi_mcs_and_small_tbs_tables_match_pinned_source() -> None:
    assert (
        tuple(
            (
                entry.index,
                entry.modulation_order,
                entry.code_rate_x1024,
                None if entry.spectral_efficiency is None else str(entry.spectral_efficiency),
            )
            for entry in CQI_TABLE_1
        )
        == CQI_TABLE_1_REFERENCE
    )
    assert (
        tuple(
            (
                entry.index,
                entry.modulation_order,
                entry.code_rate_x1024,
                str(entry.spectral_efficiency),
            )
            for entry in MCS_TABLE_1
        )
        == MCS_TABLE_1_REFERENCE
    )
    assert SMALL_TBS_TABLE == SMALL_TBS_REFERENCE


@pytest.mark.parametrize("vector", _vectors(), ids=lambda vector: vector["id"])
def test_transport_block_matches_retained_and_independent_integer_vectors(
    vector: dict[str, Any],
) -> None:
    reference = _reference_tbs(vector)
    expected = (
        vector["expected_branch"],
        Fraction(vector["expected_n_info"]),
        vector["expected_quantized_n_info_bits"],
        vector["expected_code_blocks"],
        vector["expected_tbs_bits"],
    )
    assert reference == expected

    mcs = MCS_TABLE_1[vector["mcs_index"]]
    assert mcs.modulation_order == vector["modulation_order"]
    assert mcs.code_rate_x1024 == vector["code_rate_x1024"]
    result = determine_transport_block_size(
        allocated_prbs=vector["allocated_prbs"],
        data_re_per_prb=vector["data_re_per_prb"],
        mcs=mcs,
    )
    production = (
        result.branch,
        Fraction(result.n_info_numerator, result.n_info_denominator),
        result.quantized_n_info_bits,
        result.code_block_count,
        result.transport_block_bits,
    )
    assert production == expected
