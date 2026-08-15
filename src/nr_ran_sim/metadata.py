"""Runtime environment metadata kept separate from deterministic scenario identity."""

from __future__ import annotations

import importlib.metadata
import platform
import sys
from functools import cache
from typing import Any

from nr_ran_sim import __version__

RUNTIME_DEPENDENCIES = ("numpy", "pint", "pydantic", "PyYAML")


def environment_metadata() -> dict[str, Any]:
    """Return diagnostic runtime metadata; never include it in a scenario digest."""

    dependencies = dict(_dependency_versions())
    return {
        "simulator_version": __version__,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "byteorder": sys.byteorder,
        "dependencies": dependencies,
    }


@cache
def _dependency_versions() -> tuple[tuple[str, str], ...]:
    """Resolve immutable process-wide package versions once for multi-run experiments."""

    installed: list[tuple[str, str]] = []
    for name in RUNTIME_DEPENDENCIES:
        try:
            installed.append((name, importlib.metadata.version(name)))
        except importlib.metadata.PackageNotFoundError:
            continue
    return tuple(installed)
