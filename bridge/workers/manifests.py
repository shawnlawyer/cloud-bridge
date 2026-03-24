from __future__ import annotations

from dataclasses import dataclass

from .contracts import WorkerDefinition, WorkerTask


@dataclass(frozen=True)
class DispatchPolicy:
    priority: int
    max_claims_per_cycle: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.priority, int) or self.priority < 0:
            raise ValueError("dispatch priority must be >= 0")
        if not isinstance(self.max_claims_per_cycle, int) or self.max_claims_per_cycle <= 0:
            raise ValueError("max_claims_per_cycle must be > 0")

    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "max_claims_per_cycle": self.max_claims_per_cycle,
        }


@dataclass(frozen=True)
class AdmissionRule:
    task_type: str
    required_payload_keys: tuple[str, ...] = ()
    allow_effects: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.task_type, str) or not self.task_type:
            raise ValueError("admission task_type is required")
        if not isinstance(self.required_payload_keys, tuple) or not all(
            isinstance(key, str) and key for key in self.required_payload_keys
        ):
            raise TypeError("required_payload_keys must be a tuple of non-empty strings")
        if not isinstance(self.allow_effects, bool):
            raise TypeError("allow_effects must be a boolean")

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "required_payload_keys": list(self.required_payload_keys),
            "allow_effects": self.allow_effects,
        }


@dataclass(frozen=True)
class WorkerManifest:
    definition: WorkerDefinition
    summary: str
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]
    dispatch_policy: DispatchPolicy
    admission_rules: tuple[AdmissionRule, ...]

    @property
    def worker_id(self) -> str:
        return self.definition.worker_id

    def to_dict(self) -> dict:
        return {
            "worker_id": self.definition.worker_id,
            "role": self.definition.role,
            "capabilities": list(self.definition.capabilities),
            "allowed_task_types": list(self.definition.allowed_task_types),
            "mode": self.definition.mode,
            "summary": self.summary,
            "input_keys": list(self.input_keys),
            "output_keys": list(self.output_keys),
            "dispatch_policy": self.dispatch_policy.to_dict(),
            "admission_rules": [rule.to_dict() for rule in self.admission_rules],
        }

    def admits(self, task: WorkerTask) -> tuple[bool, str | None]:
        if task.worker_id != self.worker_id:
            return False, "worker_id does not match manifest"
        if task.task_type not in self.definition.allowed_task_types:
            return False, f"task_type '{task.task_type}' is not allowed"
        if not set(task.requires).issubset(set(self.definition.capabilities)):
            return False, "task requires unsupported capabilities"

        rule = next((item for item in self.admission_rules if item.task_type == task.task_type), None)
        if rule is None:
            return False, f"no admission rule for task_type '{task.task_type}'"
        if task.effects and not rule.allow_effects:
            return False, "effects are not permitted by admission policy"

        missing_keys = [key for key in rule.required_payload_keys if key not in task.payload]
        if missing_keys:
            return False, f"missing payload keys: {', '.join(missing_keys)}"
        return True, None


DEFAULT_MANIFESTS = (
    WorkerManifest(
        definition=WorkerDefinition(
            worker_id="archivist",
            role="archivist",
            capabilities=("catalog", "summarize", "extract"),
            allowed_task_types=("catalog", "summarize"),
        ),
        summary="Indexes records and produces deterministic summaries.",
        input_keys=("records", "texts"),
        output_keys=("record_count", "records", "entry_count", "summary"),
        dispatch_policy=DispatchPolicy(priority=2, max_claims_per_cycle=1),
        admission_rules=(
            AdmissionRule(task_type="catalog", required_payload_keys=("records",)),
            AdmissionRule(task_type="summarize", required_payload_keys=("texts",)),
        ),
    ),
    WorkerManifest(
        definition=WorkerDefinition(
            worker_id="scribe",
            role="scribe",
            capabilities=("draft", "rewrite", "outline"),
            allowed_task_types=("draft", "rewrite"),
        ),
        summary="Produces bounded text drafts and rewrites.",
        input_keys=("title", "points", "text"),
        output_keys=("document",),
        dispatch_policy=DispatchPolicy(priority=3, max_claims_per_cycle=1),
        admission_rules=(
            AdmissionRule(task_type="draft", required_payload_keys=("points",)),
            AdmissionRule(task_type="rewrite", required_payload_keys=("text",)),
        ),
    ),
    WorkerManifest(
        definition=WorkerDefinition(
            worker_id="planner",
            role="planner",
            capabilities=("plan", "prioritize", "sequence"),
            allowed_task_types=("plan", "prioritize"),
        ),
        summary="Orders work into explicit deterministic steps.",
        input_keys=("items",),
        output_keys=("steps",),
        dispatch_policy=DispatchPolicy(priority=1, max_claims_per_cycle=2),
        admission_rules=(
            AdmissionRule(task_type="plan", required_payload_keys=("items",)),
            AdmissionRule(task_type="prioritize", required_payload_keys=("items",)),
        ),
    ),
    WorkerManifest(
        definition=WorkerDefinition(
            worker_id="guardian",
            role="guardian",
            capabilities=("review", "policy_check", "risk_check"),
            allowed_task_types=("review", "sanity_check"),
        ),
        summary="Checks proposals for missing constraints and risky effects.",
        input_keys=("objective", "constraints", "proposed_effects"),
        output_keys=("approved", "missing", "proposed_effects", "constraints"),
        dispatch_policy=DispatchPolicy(priority=0, max_claims_per_cycle=1),
        admission_rules=(
            AdmissionRule(task_type="review", required_payload_keys=("objective", "constraints")),
            AdmissionRule(task_type="sanity_check", required_payload_keys=("objective", "constraints")),
        ),
    ),
)


def list_default_manifests() -> tuple[WorkerManifest, ...]:
    return DEFAULT_MANIFESTS


def get_default_manifest(worker_id: str) -> WorkerManifest:
    for manifest in DEFAULT_MANIFESTS:
        if manifest.worker_id == worker_id:
            return manifest
    raise KeyError("Unknown worker manifest")
