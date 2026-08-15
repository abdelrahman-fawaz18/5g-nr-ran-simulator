"""Stable domain exceptions shared by the CLI and runtime layers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(slots=True)
class ProjectError(Exception):
    """Base class for expected, user-actionable project failures."""

    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    code: ClassVar[str] = "project_error"
    exit_code: ClassVar[int] = 1

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, "context": dict(self.context)}


class ConfigurationFileError(ProjectError):
    """Input could not be read or decoded safely."""

    code = "configuration_file_error"
    exit_code = 2


class ConfigurationValidationError(ProjectError):
    """Input structure, units, or cross-field semantics are invalid."""

    code = "configuration_validation_error"
    exit_code = 2


class ModelDomainError(ProjectError):
    """A scientific model input is outside its declared applicability domain."""

    code = "model_domain_error"
    exit_code = 2


class ArtifactError(ProjectError):
    """A requested artifact could not be committed safely."""

    code = "artifact_error"
    exit_code = 3


class InvariantViolation(ProjectError):
    """Internal simulation state violated a mandatory conservation/order rule."""

    code = "invariant_violation"
    exit_code = 4


class RunExecutionError(ProjectError):
    """A validated run could not execute within the supported mechanics domain."""

    code = "run_execution_error"
    exit_code = 5
