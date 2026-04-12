from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from bridge.workers import FileTaskStore, WorkerTask, enqueue_task

_PACKET_NAME = "research-packet.json"


def bootstrap_research_writing(
    store_root: str | Path,
    *,
    title: str,
    objective: str,
    source_paths: list[str] | tuple[str, ...] = (),
    constraints: list[str] | tuple[str, ...] = (),
    thread_id: str | None = None,
    max_attempts: int = 3,
) -> dict:
    if not isinstance(title, str) or not title:
        raise ValueError("title must be a non-empty string")
    if not isinstance(objective, str) or not objective:
        raise ValueError("objective must be a non-empty string")
    if not isinstance(max_attempts, int) or max_attempts <= 0:
        raise ValueError("max_attempts must be a positive integer")

    store = FileTaskStore(store_root)
    thread = thread_id or f"research:{_slug(title)}"
    owner_id = f"workflow:{thread}"
    source_artifacts = []
    source_packets = []
    excerpt_texts = []

    for raw_path in source_paths:
        source = Path(raw_path)
        if not source.exists() or not source.is_file():
            raise ValueError(f"source path does not exist: {source}")
        artifact = store.copy_artifact(owner_id=owner_id, source_path=source)
        excerpt = _read_excerpt(source)
        source_artifacts.append(artifact)
        source_packets.append(
            {
                "artifact_id": artifact.artifact_id,
                "name": artifact.name,
                "path": str(source),
                "excerpt": excerpt,
            }
        )
        if excerpt:
            excerpt_texts.append(f"{artifact.name}: {excerpt}")

    packet = {
        "thread_id": thread,
        "owner_id": owner_id,
        "title": title,
        "objective": objective,
        "constraints": list(constraints),
        "sources": source_packets,
        "created_at": _utc_now_text(),
    }
    packet_artifact = store.write_artifact(
        owner_id=owner_id,
        name=_PACKET_NAME,
        content=json.dumps(packet, indent=2, sort_keys=True),
        media_type="application/json",
    )

    tasks = (
        WorkerTask(
            task_id=f"{thread}:guardian",
            thread_id=thread,
            worker_id="guardian",
            task_type="review",
            payload={
                "objective": objective,
                "constraints": list(constraints),
                "proposed_effects": [],
            },
            requires=("review",),
            effects=(),
        ),
        WorkerTask(
            task_id=f"{thread}:archivist",
            thread_id=thread,
            worker_id="archivist",
            task_type="summarize",
            payload={
                "texts": excerpt_texts or [objective],
            },
            requires=("summarize",),
            effects=(),
        ),
        WorkerTask(
            task_id=f"{thread}:planner",
            thread_id=thread,
            worker_id="planner",
            task_type="plan",
            payload={
                "items": _plan_items(objective, [artifact.name for artifact in source_artifacts], constraints),
            },
            requires=("plan",),
            effects=(),
        ),
        WorkerTask(
            task_id=f"{thread}:scribe",
            thread_id=thread,
            worker_id="scribe",
            task_type="draft",
            payload={
                "title": title,
                "points": _draft_points(objective, [artifact.name for artifact in source_artifacts], constraints),
            },
            requires=("draft",),
            effects=(),
        ),
    )

    for task in tasks:
        enqueue_task(store_root, task, max_attempts=max_attempts)

    return {
        "thread_id": thread,
        "owner_id": owner_id,
        "task_count": len(tasks),
        "task_ids": [task.task_id for task in tasks],
        "artifact_count": len(source_artifacts) + 1,
        "artifact_ids": [packet_artifact.artifact_id, *[artifact.artifact_id for artifact in source_artifacts]],
        "packet_artifact_id": packet_artifact.artifact_id,
    }


def describe_research_writing(store_root: str | Path, thread_id: str) -> dict:
    store = FileTaskStore(store_root)
    owner_id = f"workflow:{thread_id}"
    tasks = [record for record in store.list_tasks() if record.task.thread_id == thread_id]
    artifacts = list(store.list_artifacts(owner_id=owner_id))
    counts = Counter(record.status for record in tasks)
    packet = _load_packet(store, artifacts)
    return {
        "thread_id": thread_id,
        "owner_id": owner_id,
        "title": packet.get("title", thread_id),
        "objective": packet.get("objective", ""),
        "constraints": packet.get("constraints", []),
        "sources": packet.get("sources", []),
        "task_count": len(tasks),
        "task_counts": dict(sorted(counts.items())),
        "tasks": [record.to_dict() for record in tasks],
        "artifact_count": len(artifacts),
        "artifacts": [artifact.to_dict() for artifact in artifacts],
    }


def assemble_research_writing(store_root: str | Path, thread_id: str, name: str | None = None) -> dict:
    store = FileTaskStore(store_root)
    state = describe_research_writing(store_root, thread_id)
    owner_id = state["owner_id"]
    tasks_by_worker = {task["task"]["worker_id"]: task for task in state["tasks"]}

    title = state["title"]
    objective = state["objective"]
    constraints = state["constraints"]
    sources = state["sources"]

    lines = [f"# {title}", "", "## Objective", objective or "Pending objective.", ""]
    if constraints:
        lines.extend(["## Constraints", *[f"- {item}" for item in constraints], ""])
    if sources:
        lines.append("## Source Material")
        for source in sources:
            lines.append(f"- {source['name']}")
        lines.append("")

    guardian = tasks_by_worker.get("guardian", {}).get("result") or {}
    if guardian:
        output = guardian.get("output", {})
        lines.extend(
            [
                "## Guardian Review",
                f"- Approved: {output.get('approved', False)}",
                f"- Missing: {', '.join(output.get('missing', [])) or 'none'}",
                "",
            ]
        )

    archivist = tasks_by_worker.get("archivist", {}).get("result") or {}
    if archivist:
        output = archivist.get("output", {})
        lines.extend(["## Research Digest", output.get("summary", "Pending summary."), ""])

    planner = tasks_by_worker.get("planner", {}).get("result") or {}
    if planner:
        lines.append("## Working Plan")
        for step in planner.get("output", {}).get("steps", []):
            lines.append(f"{step['order']}. {step['item']}")
        lines.append("")

    scribe = tasks_by_worker.get("scribe", {}).get("result") or {}
    if scribe:
        lines.extend(["## Draft", scribe.get("output", {}).get("document", "Pending draft."), ""])

    document = "\n".join(lines).strip() + "\n"
    artifact = store.write_artifact(
        owner_id=owner_id,
        name=name or f"{_slug(title)}-draft.md",
        content=document,
        media_type="text/markdown",
    )
    return {
        "thread_id": thread_id,
        "artifact": artifact.to_dict(),
        "included_workers": sorted(worker_id for worker_id, task in tasks_by_worker.items() if task.get("result")),
    }


def _plan_items(objective: str, source_names: list[str], constraints: list[str] | tuple[str, ...]) -> list[str]:
    items = [f"Clarify objective: {objective}"]
    items.extend(f"Read source: {name}" for name in source_names)
    items.extend(f"Honor constraint: {item}" for item in constraints)
    items.extend(["Extract core claims", "Outline the argument", "Draft the first pass"])
    return items


def _draft_points(objective: str, source_names: list[str], constraints: list[str] | tuple[str, ...]) -> list[str]:
    points = [objective]
    points.extend(f"Use source: {name}" for name in source_names)
    points.extend(f"Constraint: {item}" for item in constraints)
    return points


def _load_packet(store: FileTaskStore, artifacts: list) -> dict:
    packet_artifact = next((artifact for artifact in artifacts if artifact.name == _PACKET_NAME), None)
    if packet_artifact is None:
        return {}
    try:
        return json.loads(store.read_artifact_text(packet_artifact.artifact_id))
    except (json.JSONDecodeError, KeyError):
        return {}


def _read_excerpt(path: Path, max_chars: int = 1200) -> str:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    collapsed = re.sub(r"\s+", " ", text)
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1].rstrip() + "…"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48] or "project"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
