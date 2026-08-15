"""Pinned Release 18 NR Table 1 and small-TBS source data."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final


@dataclass(frozen=True, slots=True)
class CqiTableEntry:
    index: int
    modulation: str | None
    modulation_order: int | None
    code_rate_x1024: int | None
    spectral_efficiency: Decimal | None

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "modulation": self.modulation,
            "modulation_order": self.modulation_order,
            "code_rate_x1024": self.code_rate_x1024,
            "spectral_efficiency": (
                None if self.spectral_efficiency is None else float(self.spectral_efficiency)
            ),
        }


@dataclass(frozen=True, slots=True)
class McsTableEntry:
    index: int
    modulation: str
    modulation_order: int
    code_rate_x1024: int
    spectral_efficiency: Decimal

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "modulation": self.modulation,
            "modulation_order": self.modulation_order,
            "code_rate_x1024": self.code_rate_x1024,
            "spectral_efficiency": float(self.spectral_efficiency),
        }


def _cqi(
    index: int,
    modulation: str,
    modulation_order: int,
    code_rate_x1024: int,
    efficiency: str,
) -> CqiTableEntry:
    return CqiTableEntry(
        index,
        modulation,
        modulation_order,
        code_rate_x1024,
        Decimal(efficiency),
    )


def _mcs(
    index: int,
    modulation: str,
    modulation_order: int,
    code_rate_x1024: int,
    efficiency: str,
) -> McsTableEntry:
    return McsTableEntry(
        index,
        modulation,
        modulation_order,
        code_rate_x1024,
        Decimal(efficiency),
    )


# TS 38.214 V18.9.0 Table 5.2.2.1-2, including the out-of-range row 0.
CQI_TABLE_1: Final[tuple[CqiTableEntry, ...]] = (
    CqiTableEntry(0, None, None, None, None),
    _cqi(1, "QPSK", 2, 78, "0.1523"),
    _cqi(2, "QPSK", 2, 120, "0.2344"),
    _cqi(3, "QPSK", 2, 193, "0.3770"),
    _cqi(4, "QPSK", 2, 308, "0.6016"),
    _cqi(5, "QPSK", 2, 449, "0.8770"),
    _cqi(6, "QPSK", 2, 602, "1.1758"),
    _cqi(7, "16QAM", 4, 378, "1.4766"),
    _cqi(8, "16QAM", 4, 490, "1.9141"),
    _cqi(9, "16QAM", 4, 616, "2.4063"),
    _cqi(10, "64QAM", 6, 466, "2.7305"),
    _cqi(11, "64QAM", 6, 567, "3.3223"),
    _cqi(12, "64QAM", 6, 666, "3.9023"),
    _cqi(13, "64QAM", 6, 772, "4.5234"),
    _cqi(14, "64QAM", 6, 873, "5.1152"),
    _cqi(15, "64QAM", 6, 948, "5.5547"),
)


# TS 38.214 V18.9.0 Table 5.1.3.1-1. Reserved indices 29-31 are excluded.
MCS_TABLE_1: Final[tuple[McsTableEntry, ...]] = (
    _mcs(0, "QPSK", 2, 120, "0.2344"),
    _mcs(1, "QPSK", 2, 157, "0.3066"),
    _mcs(2, "QPSK", 2, 193, "0.3770"),
    _mcs(3, "QPSK", 2, 251, "0.4902"),
    _mcs(4, "QPSK", 2, 308, "0.6016"),
    _mcs(5, "QPSK", 2, 379, "0.7402"),
    _mcs(6, "QPSK", 2, 449, "0.8770"),
    _mcs(7, "QPSK", 2, 526, "1.0273"),
    _mcs(8, "QPSK", 2, 602, "1.1758"),
    _mcs(9, "QPSK", 2, 679, "1.3262"),
    _mcs(10, "16QAM", 4, 340, "1.3281"),
    _mcs(11, "16QAM", 4, 378, "1.4766"),
    _mcs(12, "16QAM", 4, 434, "1.6953"),
    _mcs(13, "16QAM", 4, 490, "1.9141"),
    _mcs(14, "16QAM", 4, 553, "2.1602"),
    _mcs(15, "16QAM", 4, 616, "2.4063"),
    _mcs(16, "16QAM", 4, 658, "2.5703"),
    _mcs(17, "64QAM", 6, 438, "2.5664"),
    _mcs(18, "64QAM", 6, 466, "2.7305"),
    _mcs(19, "64QAM", 6, 517, "3.0293"),
    _mcs(20, "64QAM", 6, 567, "3.3223"),
    _mcs(21, "64QAM", 6, 616, "3.6094"),
    _mcs(22, "64QAM", 6, 666, "3.9023"),
    _mcs(23, "64QAM", 6, 719, "4.2129"),
    _mcs(24, "64QAM", 6, 772, "4.5234"),
    _mcs(25, "64QAM", 6, 822, "4.8164"),
    _mcs(26, "64QAM", 6, 873, "5.1152"),
    _mcs(27, "64QAM", 6, 910, "5.3320"),
    _mcs(28, "64QAM", 6, 948, "5.5547"),
)

RESERVED_MCS_TABLE_1_INDICES: Final[tuple[int, ...]] = (29, 30, 31)


# TS 38.214 V18.9.0 Table 5.1.3.2-1.
SMALL_TBS_TABLE: Final[tuple[int, ...]] = (
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
