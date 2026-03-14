from __future__ import annotations

from dataclasses import dataclass

from .contracts import WorkerDefinition


@dataclass(frozen=True)
class WorkerManifest:
    definition: WorkerDefinition
    summary: str
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]

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
        }


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
    ),
)


def list_default_manifests() -> tuple[WorkerManifest, ...]:
    return DEFAULT_MANIFESTS


def get_default_manifest(worker_id: str) -> WorkerManifest:
    for manifest in DEFAULT_MANIFESTS:
        if manifest.worker_id == worker_id:
            return manifest
    raise KeyError("Unknown worker manifest")
