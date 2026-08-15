"""Canonical JSON serialization and deterministic scenario identity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from nr_ran_sim.config.normalize import NormalizedScenario
from nr_ran_sim.errors import ArtifactError


@dataclass(frozen=True, slots=True)
class ManifestEnvelope:
    """A normalized scenario plus its content-derived identity."""

    configuration_sha256: str
    normalized: NormalizedScenario

    def as_dict(self) -> dict[str, Any]:
        return {
            "configuration_sha256": self.configuration_sha256,
            "normalized": _canonical_value(self.normalized.model_dump(mode="python")),
        }

    def to_json(self) -> str:
        return (
            json.dumps(
                self.as_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        )

    def write(self, path: Path, *, force: bool = False) -> None:
        """Atomically create a manifest without silently overwriting an artifact."""

        if path.exists() and not force:
            raise ArtifactError(
                "output manifest already exists; pass --force to replace it",
                {"path": str(path)},
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_text(self.to_json(), encoding="utf-8", newline="\n")
            temporary.replace(path)
        except OSError as exc:
            raise ArtifactError(
                "unable to commit normalized manifest",
                {"path": str(path), "detail": str(exc)},
            ) from exc
        finally:
            if temporary.exists():
                temporary.unlink()


def build_manifest(normalized: NormalizedScenario) -> ManifestEnvelope:
    """Build a canonical envelope whose digest covers normalized scientific content."""

    content = canonical_content_bytes(normalized)
    return ManifestEnvelope(
        configuration_sha256=hashlib.sha256(content).hexdigest(),
        normalized=normalized,
    )


def canonical_content_bytes(normalized: NormalizedScenario) -> bytes:
    """Return canonical UTF-8 bytes used for the configuration digest."""

    return canonical_json_bytes(normalized.model_dump(mode="python"))


def canonical_json_bytes(value: Any) -> bytes:
    """Return the project's canonical JSON encoding for an arbitrary semantic payload."""

    payload = _canonical_value(value)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("canonical JSON cannot represent a non-finite decimal")
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")
