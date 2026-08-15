"""Order-independent semantic seed derivation from ADR-0003."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
from dataclasses import dataclass
from typing import Final

import numpy as np

from nr_ran_sim.errors import ConfigurationValidationError, InvariantViolation

MASTER_SEED = re.compile(r"^0x[0-9a-fA-F]{32}$")
SEMANTIC_PATH = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,254}$")
DERIVATION_VERSION: Final = "sha256-semantic-v1"


@dataclass(frozen=True, slots=True)
class SeedFingerprint:
    derivation_version: str
    semantic_path: str
    fingerprint: str
    seed_words: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RngStreamRecord:
    """Serializable provenance for one owned semantic random stream."""

    semantic_path: str
    owner: str
    engine: str
    numpy_version: str
    derivation_version: str
    fingerprint: str
    seed_words: tuple[int, ...]


class OwnedRng:
    """A NumPy generator whose semantic path has one explicit owner."""

    __slots__ = ("_generator", "record")

    def __init__(self, record: RngStreamRecord, generator: np.random.Generator) -> None:
        self.record = record
        self._generator = generator

    def exponential(self, mean: float) -> float:
        return float(self._generator.exponential(mean))

    def uniform(self, minimum: float, maximum: float) -> float:
        return float(self._generator.uniform(minimum, maximum))

    def standard_uniform(self) -> float:
        return float(self._generator.random())

    def normal(self, mean: float, standard_deviation: float) -> float:
        return float(self._generator.normal(mean, standard_deviation))

    def integer_inclusive(self, minimum: int, maximum: int) -> int:
        return int(self._generator.integers(minimum, maximum, endpoint=True))


class SemanticRngRegistry:
    """Issue order-independent PCG64DXSM streams and retain their seed manifest."""

    def __init__(self, baseline_id: str, master_seed: str, replication_id: int) -> None:
        # Validate invariant inputs before any stream can be acquired.
        derive_seed_fingerprint(baseline_id, master_seed, replication_id, "registry/validation")
        self._baseline_id = baseline_id
        self._master_seed = master_seed
        self._replication_id = replication_id
        self._records: dict[str, RngStreamRecord] = {}

    def acquire(self, semantic_path: str, *, owner: str) -> OwnedRng:
        if semantic_path in self._records:
            raise InvariantViolation(
                "semantic RNG stream already has an owner",
                {
                    "semantic_path": semantic_path,
                    "existing_owner": self._records[semantic_path].owner,
                    "requested_owner": owner,
                    "requirement": "QOS-005",
                },
            )
        fingerprint = derive_seed_fingerprint(
            self._baseline_id,
            self._master_seed,
            self._replication_id,
            semantic_path,
        )
        record = RngStreamRecord(
            semantic_path=semantic_path,
            owner=owner,
            engine="PCG64DXSM",
            numpy_version=importlib.metadata.version("numpy"),
            derivation_version=fingerprint.derivation_version,
            fingerprint=fingerprint.fingerprint,
            seed_words=fingerprint.seed_words,
        )
        seed_sequence = np.random.SeedSequence(fingerprint.seed_words)
        self._records[semantic_path] = record
        return OwnedRng(record, np.random.Generator(np.random.PCG64DXSM(seed_sequence)))

    def manifest(self) -> tuple[RngStreamRecord, ...]:
        return tuple(self._records[path] for path in sorted(self._records))


def derive_seed_fingerprint(
    baseline_id: str,
    master_seed: str,
    replication_id: int,
    semantic_path: str,
) -> SeedFingerprint:
    """Derive fixed-width seed words without construction-order coupling."""

    if not MASTER_SEED.fullmatch(master_seed):
        raise ConfigurationValidationError(
            "master seed must be a 128-bit hexadecimal string prefixed by 0x",
            {"field": "master_seed", "requirement": "EXP-002"},
        )
    if replication_id < 0:
        raise ConfigurationValidationError(
            "replication ID must be nonnegative",
            {"field": "replication_id", "requirement": "EXP-002"},
        )
    if not SEMANTIC_PATH.fullmatch(semantic_path):
        raise ConfigurationValidationError(
            "semantic RNG path contains unsupported characters",
            {"field": "semantic_path", "requirement": "EXP-002"},
        )
    payload = json.dumps(
        {
            "baseline_id": baseline_id,
            "derivation_version": DERIVATION_VERSION,
            "master_seed": master_seed.lower(),
            "replication_id": replication_id,
            "semantic_path": semantic_path,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    digest = hashlib.sha256(payload).digest()
    words = tuple(int.from_bytes(digest[index : index + 4], "big") for index in range(0, 32, 4))
    return SeedFingerprint(
        derivation_version=DERIVATION_VERSION,
        semantic_path=semantic_path,
        fingerprint=digest.hex()[:16],
        seed_words=words,
    )
