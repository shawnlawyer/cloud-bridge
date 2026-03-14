from __future__ import annotations

from collections.abc import Callable

from .contracts import WorkerDefinition, WorkerResult, WorkerTask
from .manifests import list_default_manifests

WorkerHandler = Callable[[WorkerTask], dict]


class LocalWorkerRunner:
    def __init__(self) -> None:
        self._definitions: dict[str, WorkerDefinition] = {}
        self._handlers: dict[str, WorkerHandler] = {}

    def register(self, definition: WorkerDefinition, handler: WorkerHandler) -> None:
        if definition.worker_id in self._definitions:
            raise ValueError("Worker already registered")
        self._definitions[definition.worker_id] = definition
        self._handlers[definition.worker_id] = handler

    def get(self, worker_id: str) -> WorkerDefinition:
        if worker_id not in self._definitions:
            raise KeyError("Unknown worker")
        return self._definitions[worker_id]

    def list_workers(self) -> tuple[WorkerDefinition, ...]:
        return tuple(self._definitions[worker_id] for worker_id in sorted(self._definitions))

    def run(self, task: WorkerTask) -> WorkerResult:
        definition = self.get(task.worker_id)

        rejection = self._rejection_reason(definition, task)
        if rejection is not None:
            return WorkerResult(
                task_id=task.task_id,
                worker_id=definition.worker_id,
                role=definition.role,
                status="rejected",
                output={},
                notes=(rejection,),
            )

        output = self._handlers[definition.worker_id](task)
        if not isinstance(output, dict):
            raise TypeError("worker handler must return a dict")

        return WorkerResult(
            task_id=task.task_id,
            worker_id=definition.worker_id,
            role=definition.role,
            status="completed",
            output=output,
            notes=(),
        )

    @staticmethod
    def _rejection_reason(definition: WorkerDefinition, task: WorkerTask) -> str | None:
        if task.effects:
            return "side effects are not permitted"
        if task.task_type not in definition.allowed_task_types:
            return f"task_type '{task.task_type}' is not allowed for worker '{task.worker_id}'"
        missing = tuple(capability for capability in task.requires if capability not in definition.capabilities)
        if missing:
            return f"missing worker capabilities: {', '.join(missing)}"
        return None


def _archivist_handler(task: WorkerTask) -> dict:
    if task.task_type == "catalog":
        records = task.payload.get("records", [])
        if not isinstance(records, list) or not all(isinstance(value, str) for value in records):
            raise ValueError("archivist catalog payload.records must be a list of strings")
        return {
            "record_count": len(records),
            "records": sorted(records),
        }

    texts = task.payload.get("texts", [])
    if not isinstance(texts, list) or not all(isinstance(value, str) for value in texts):
        raise ValueError("archivist summarize payload.texts must be a list of strings")
    return {
        "entry_count": len(texts),
        "summary": " | ".join(texts),
    }


def _scribe_handler(task: WorkerTask) -> dict:
    if task.task_type == "draft":
        title = task.payload.get("title", "Untitled")
        points = task.payload.get("points", [])
        if not isinstance(title, str):
            raise ValueError("scribe draft payload.title must be a string")
        if not isinstance(points, list) or not all(isinstance(value, str) for value in points):
            raise ValueError("scribe draft payload.points must be a list of strings")
        lines = [f"# {title}", ""]
        lines.extend(f"- {point}" for point in points)
        return {"document": "\n".join(lines)}

    text = task.payload.get("text", "")
    if not isinstance(text, str):
        raise ValueError("scribe rewrite payload.text must be a string")
    return {"document": text.strip()}


def _planner_handler(task: WorkerTask) -> dict:
    items = task.payload.get("items", [])
    if not isinstance(items, list) or not all(isinstance(value, str) for value in items):
        raise ValueError("planner payload.items must be a list of strings")
    steps = [{"order": index + 1, "item": item} for index, item in enumerate(items)]
    if task.task_type == "prioritize":
        steps = sorted(steps, key=lambda step: step["item"])
        steps = [{"order": index + 1, "item": step["item"]} for index, step in enumerate(steps)]
    return {"steps": steps}


def _guardian_handler(task: WorkerTask) -> dict:
    proposed_effects = task.payload.get("proposed_effects", [])
    constraints = task.payload.get("constraints", [])
    if not isinstance(proposed_effects, list) or not all(
        isinstance(value, str) for value in proposed_effects
    ):
        raise ValueError("guardian payload.proposed_effects must be a list of strings")
    if not isinstance(constraints, list) or not all(isinstance(value, str) for value in constraints):
        raise ValueError("guardian payload.constraints must be a list of strings")

    missing = []
    if "objective" not in task.payload:
        missing.append("objective")
    if "constraints" not in task.payload:
        missing.append("constraints")

    approved = not proposed_effects and not missing
    return {
        "approved": approved,
        "missing": missing,
        "proposed_effects": proposed_effects,
        "constraints": constraints,
    }


def build_default_runner() -> LocalWorkerRunner:
    runner = LocalWorkerRunner()
    handlers: dict[str, WorkerHandler] = {
        "archivist": _archivist_handler,
        "scribe": _scribe_handler,
        "planner": _planner_handler,
        "guardian": _guardian_handler,
    }
    for manifest in list_default_manifests():
        runner.register(manifest.definition, handlers[manifest.worker_id])
    return runner
