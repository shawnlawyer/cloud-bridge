from __future__ import annotations

from dataclasses import dataclass, field
import re

KNOWN_ROLES = ("archivist", "scribe", "planner", "guardian")
_STATUS_VALUES = frozenset({"completed", "rejected"})
_MODE_VALUES = frozenset({"analysis-only"})
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,127}$")


def _validate_identifier(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} is required")
    if _IDENTIFIER_RE.match(value) is None:
        raise ValueError(f"{field_name} format is invalid")


def _coerce_string_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, list):
        values = tuple(values)
    if not isinstance(values, tuple) or not all(isinstance(value, str) for value in values):
        raise TypeError(f"{field_name} must be a list or tuple of strings")
    return values


@dataclass(frozen=True)
class WorkerTask:
    task_id: str = ""
    thread_id: str = ""
    worker_id: str = ""
    task_type: str = ""
    payload: dict = field(default_factory=dict)
    requires: tuple[str, ...] | list[str] = ()
    effects: tuple[str, ...] | list[str] = ()

    def __post_init__(self) -> None:
        _validate_identifier("task_id", self.task_id)
        _validate_identifier("thread_id", self.thread_id)
        _validate_identifier("worker_id", self.worker_id)
        _validate_identifier("task_type", self.task_type)
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dict")

        object.__setattr__(self, "requires", _coerce_string_tuple("requires", self.requires))
        object.__setattr__(self, "effects", _coerce_string_tuple("effects", self.effects))

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "thread_id": self.thread_id,
            "worker_id": self.worker_id,
            "task_type": self.task_type,
            "payload": self.payload,
            "requires": list(self.requires),
            "effects": list(self.effects),
        }


@dataclass(frozen=True)
class WorkerDefinition:
    worker_id: str = ""
    role: str = ""
    capabilities: tuple[str, ...] | list[str] = ()
    allowed_task_types: tuple[str, ...] | list[str] = ()
    mode: str = "analysis-only"

    def __post_init__(self) -> None:
        _validate_identifier("worker_id", self.worker_id)
        if self.role not in KNOWN_ROLES:
            raise ValueError(f"Unknown worker role: {self.role}")
        object.__setattr__(
            self,
            "capabilities",
            _coerce_string_tuple("capabilities", self.capabilities),
        )
        object.__setattr__(
            self,
            "allowed_task_types",
            _coerce_string_tuple("allowed_task_types", self.allowed_task_types),
        )
        if not self.capabilities:
            raise ValueError("capabilities are required")
        if not self.allowed_task_types:
            raise ValueError("allowed_task_types are required")
        if self.mode not in _MODE_VALUES:
            raise ValueError(f"Unsupported worker mode: {self.mode}")

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "role": self.role,
            "capabilities": list(self.capabilities),
            "allowed_task_types": list(self.allowed_task_types),
            "mode": self.mode,
        }


@dataclass(frozen=True)
class WorkerResult:
    task_id: str = ""
    worker_id: str = ""
    role: str = ""
    status: str = ""
    output: dict = field(default_factory=dict)
    notes: tuple[str, ...] | list[str] = ()

    def __post_init__(self) -> None:
        _validate_identifier("task_id", self.task_id)
        _validate_identifier("worker_id", self.worker_id)
        if self.role not in KNOWN_ROLES:
            raise ValueError(f"Unknown worker role: {self.role}")
        if self.status not in _STATUS_VALUES:
            raise ValueError(f"Unsupported worker status: {self.status}")
        if not isinstance(self.output, dict):
            raise TypeError("output must be a dict")
        object.__setattr__(self, "notes", _coerce_string_tuple("notes", self.notes))

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "role": self.role,
            "status": self.status,
            "output": self.output,
            "notes": list(self.notes),
        }
