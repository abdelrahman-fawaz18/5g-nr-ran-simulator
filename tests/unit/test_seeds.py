import pytest

from nr_ran_sim.errors import ConfigurationValidationError
from nr_ran_sim.experiments.seeds import SemanticRngRegistry, derive_seed_fingerprint

MASTER = "0x0123456789abcdeffedcba9876543210"


def test_semantic_seed_derivation_is_stable_and_path_scoped() -> None:
    first = derive_seed_fingerprint("baseline", MASTER, 7, "traffic/ue-7/interarrival")
    replay = derive_seed_fingerprint(
        "baseline", MASTER.upper().replace("0X", "0x"), 7, "traffic/ue-7/interarrival"
    )
    other = derive_seed_fingerprint("baseline", MASTER, 7, "traffic/ue-8/interarrival")
    assert first == replay
    assert first != other
    assert first.derivation_version == "sha256-semantic-v1"
    assert len(first.fingerprint) == 16
    assert len(first.seed_words) == 8
    assert all(0 <= word < 2**32 for word in first.seed_words)


@pytest.mark.parametrize(
    ("master", "replication", "path"),
    [
        ("1234", 0, "traffic/ue"),
        (MASTER, -1, "traffic/ue"),
        (MASTER, 0, "bad path!"),
    ],
)
def test_seed_input_contract_fails_closed(master: str, replication: int, path: str) -> None:
    with pytest.raises(ConfigurationValidationError):
        derive_seed_fingerprint("baseline", master, replication, path)


def test_rng_manifest_records_engine_version_path_and_seed_material() -> None:
    registry = SemanticRngRegistry("baseline", MASTER, 7)
    stream = registry.acquire("traffic/ue-7/interarrival", owner="bearer/ue-7")
    record = registry.manifest()[0]
    assert stream.record == record
    assert record.engine == "PCG64DXSM"
    assert record.numpy_version
    assert record.owner == "bearer/ue-7"
    assert len(record.seed_words) == 8


def test_radio_rng_primitives_replay_exactly() -> None:
    first = SemanticRngRegistry("baseline", MASTER, 7).acquire("link/a/b/radio", owner="test")
    replay = SemanticRngRegistry("baseline", MASTER, 7).acquire("link/a/b/radio", owner="test")
    first_values = (
        first.standard_uniform(),
        first.normal(0.0, 4.0),
        first.integer_inclusive(1, 5),
    )
    replay_values = (
        replay.standard_uniform(),
        replay.normal(0.0, 4.0),
        replay.integer_inclusive(1, 5),
    )
    assert first_values == replay_values
    assert 0.0 <= first_values[0] < 1.0
    assert 1 <= first_values[2] <= 5
