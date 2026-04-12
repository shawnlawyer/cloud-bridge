from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from bridge.workers import FileTaskStore, WorkerTask, enqueue_task

_PACKET_NAME = "research-packet.json"
_TEXT_SOURCE_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".html",
    ".htm",
    ".xml",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
}


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
    source_artifacts, source_packets, excerpt_texts = _import_source_artifacts(store, owner_id, source_paths)
    packet_artifact = _write_packet(
        store,
        owner_id=owner_id,
        thread_id=thread,
        title=title,
        objective=objective,
        constraints=constraints,
        source_packets=source_packets,
    )
    tasks = _build_workflow_tasks(
        thread,
        title=title,
        objective=objective,
        constraints=constraints,
        source_artifacts=source_artifacts,
        excerpt_texts=excerpt_texts,
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


def bootstrap_research_writing_from_folder(
    store_root: str | Path,
    *,
    folder_path: str | Path,
    title: str,
    objective: str,
    constraints: list[str] | tuple[str, ...] = (),
    thread_id: str | None = None,
    max_attempts: int = 3,
    max_files: int = 64,
    max_bytes: int = 1_000_000,
) -> dict:
    collected = collect_research_writing_sources(folder_path, max_files=max_files, max_bytes=max_bytes)
    source_paths = collected["source_paths"]
    skipped = collected["skipped"]
    if not source_paths:
        raise ValueError("folder does not contain any supported source files")

    out = bootstrap_research_writing(
        store_root,
        title=title,
        objective=objective,
        source_paths=source_paths,
        constraints=constraints,
        thread_id=thread_id,
        max_attempts=max_attempts,
    )
    out["source_count"] = len(source_paths)
    out["source_paths"] = source_paths
    out["skipped"] = skipped
    return out


def refresh_research_writing(
    store_root: str | Path,
    *,
    thread_id: str,
    source_paths: list[str] | tuple[str, ...] = (),
    title: str | None = None,
    objective: str | None = None,
    constraints: list[str] | tuple[str, ...] | None = None,
    max_attempts: int = 3,
) -> dict:
    if not isinstance(thread_id, str) or not thread_id:
        raise ValueError("thread_id must be a non-empty string")
    if title is not None and (not isinstance(title, str) or not title):
        raise ValueError("title must be a non-empty string when provided")
    if objective is not None and (not isinstance(objective, str) or not objective):
        raise ValueError("objective must be a non-empty string when provided")
    if constraints is not None and (
        not isinstance(constraints, (list, tuple)) or not all(isinstance(item, str) and item for item in constraints)
    ):
        raise ValueError("constraints must be a list or tuple of non-empty strings when provided")
    if not isinstance(max_attempts, int) or max_attempts <= 0:
        raise ValueError("max_attempts must be a positive integer")

    store = FileTaskStore(store_root)
    owner_id = f"workflow:{thread_id}"
    packet = _load_packet(store, list(store.list_artifacts(owner_id=owner_id)))
    resolved_title = title or packet.get("title")
    resolved_objective = objective or packet.get("objective")
    resolved_constraints = list(constraints) if constraints is not None else list(packet.get("constraints", []))
    if not resolved_title:
        raise ValueError("title is required when the workflow packet is missing")
    if not resolved_objective:
        raise ValueError("objective is required when the workflow packet is missing")

    source_artifacts, source_packets, excerpt_texts = _import_source_artifacts(store, owner_id, source_paths)
    packet_artifact = _write_packet(
        store,
        owner_id=owner_id,
        thread_id=thread_id,
        title=resolved_title,
        objective=resolved_objective,
        constraints=resolved_constraints,
        source_packets=source_packets,
    )
    revision = _revision_token()
    tasks = _build_workflow_tasks(
        thread_id,
        title=resolved_title,
        objective=resolved_objective,
        constraints=resolved_constraints,
        source_artifacts=source_artifacts,
        excerpt_texts=excerpt_texts,
        revision=revision,
    )
    for task in tasks:
        enqueue_task(store_root, task, max_attempts=max_attempts)

    return {
        "thread_id": thread_id,
        "owner_id": owner_id,
        "task_count": len(tasks),
        "task_ids": [task.task_id for task in tasks],
        "artifact_count": len(source_artifacts) + 1,
        "artifact_ids": [packet_artifact.artifact_id, *[artifact.artifact_id for artifact in source_artifacts]],
        "packet_artifact_id": packet_artifact.artifact_id,
        "revision": revision,
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


def list_research_writing(store_root: str | Path) -> list[dict]:
    store = FileTaskStore(store_root)
    packet_artifacts_by_owner: dict[str, object] = {}
    for artifact in store.list_artifacts():
        if artifact.name != _PACKET_NAME or not artifact.owner_id.startswith("workflow:"):
            continue
        current = packet_artifacts_by_owner.get(artifact.owner_id)
        if current is None or artifact.created_at > current.created_at:
            packet_artifacts_by_owner[artifact.owner_id] = artifact

    workflows = []
    for owner_id, artifact in packet_artifacts_by_owner.items():
        packet = _load_packet(store, [artifact])
        thread_id = packet.get("thread_id")
        if not thread_id:
            continue
        tasks = [record for record in store.list_tasks() if record.task.thread_id == thread_id]
        counts = Counter(record.status for record in tasks)
        workflow_artifacts = list(store.list_artifacts(owner_id=owner_id))
        latest_draft = _latest_artifact(workflow_artifacts, lambda item: item.name.endswith(".md"))
        workflows.append(
            {
                "thread_id": thread_id,
                "owner_id": owner_id,
                "title": packet.get("title", thread_id),
                "objective": packet.get("objective", ""),
                "constraints": packet.get("constraints", []),
                "source_count": len(packet.get("sources", [])),
                "task_count": len(tasks),
                "task_counts": dict(sorted(counts.items())),
                "artifact_count": len(workflow_artifacts),
                "latest_draft_artifact_id": latest_draft.artifact_id if latest_draft else None,
                "created_at": packet.get("created_at"),
            }
        )
    workflows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return workflows


def assemble_research_writing(store_root: str | Path, thread_id: str, name: str | None = None) -> dict:
    store = FileTaskStore(store_root)
    state = describe_research_writing(store_root, thread_id)
    owner_id = state["owner_id"]
    tasks_by_worker = {}
    for task in sorted(state["tasks"], key=lambda item: item["task"]["task_id"]):
        if task.get("result"):
            tasks_by_worker[task["task"]["worker_id"]] = task

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


def collect_research_writing_sources(
    folder_path: str | Path,
    *,
    max_files: int = 64,
    max_bytes: int = 1_000_000,
) -> dict:
    if not isinstance(max_files, int) or max_files <= 0:
        raise ValueError("max_files must be a positive integer")
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")

    root = Path(folder_path)
    if not root.exists() or not root.is_dir():
        raise ValueError("folder_path must point to an existing directory")

    source_paths = []
    skipped = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() not in _TEXT_SOURCE_SUFFIXES:
            skipped.append({"path": str(path), "reason": "unsupported suffix"})
            continue
        size = path.stat().st_size
        if size > max_bytes:
            skipped.append({"path": str(path), "reason": f"exceeds {max_bytes} bytes"})
            continue
        if len(source_paths) >= max_files:
            skipped.append({"path": str(path), "reason": f"exceeds max_files limit {max_files}"})
            continue
        source_paths.append(str(path))
    return {"source_paths": source_paths, "skipped": skipped}


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


def _import_source_artifacts(
    store: FileTaskStore,
    owner_id: str,
    source_paths: list[str] | tuple[str, ...],
) -> tuple[list, list[dict], list[str]]:
    if not isinstance(source_paths, (list, tuple)) or not all(isinstance(path, str) and path for path in source_paths):
        raise ValueError("source_paths must be a list or tuple of non-empty strings")

    source_artifacts = []
    source_packets = []
    excerpt_texts = []
    for raw_path in source_paths:
        source = Path(raw_path)
        if not source.exists() or not source.is_file():
            raise ValueError(f"source path does not exist: {source}")
        artifact = store.copy_artifact(owner_id=owner_id, source_path=source, name=str(source))
        stat = source.stat()
        excerpt = _read_excerpt(source)
        source_artifacts.append(artifact)
        source_packets.append(
            {
                "artifact_id": artifact.artifact_id,
                "name": artifact.name,
                "path": str(source),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "excerpt": excerpt,
            }
        )
        excerpt_texts.append(excerpt)
    return source_artifacts, source_packets, excerpt_texts


def _write_packet(
    store: FileTaskStore,
    *,
    owner_id: str,
    thread_id: str,
    title: str,
    objective: str,
    constraints: list[str] | tuple[str, ...],
    source_packets: list[dict],
):
    packet = {
        "thread_id": thread_id,
        "title": title,
        "objective": objective,
        "constraints": list(constraints),
        "sources": source_packets,
        "created_at": _utc_now_text(),
    }
    return store.write_artifact(
        owner_id=owner_id,
        name=_PACKET_NAME,
        content=json.dumps(packet, indent=2, sort_keys=True),
        media_type="application/json",
    )


def _build_workflow_tasks(
    thread_id: str,
    *,
    title: str,
    objective: str,
    constraints: list[str] | tuple[str, ...],
    source_artifacts: list,
    excerpt_texts: list[str],
    revision: str | None = None,
) -> tuple[WorkerTask, ...]:
    suffix = f":{revision}" if revision else ""
    source_names = [artifact.name for artifact in source_artifacts]
    source_artifact_ids = [artifact.artifact_id for artifact in source_artifacts]
    plan_items = _plan_items(objective, source_names, constraints)
    draft_points = _draft_points(objective, source_names, constraints)
    return (
        WorkerTask(
            task_id=f"{thread_id}:guardian{suffix}",
            thread_id=thread_id,
            worker_id="guardian",
            task_type="review",
            payload={
                "objective": objective,
                "constraints": list(constraints),
                "proposed_effects": [],
                "source_artifact_ids": source_artifact_ids,
            },
            requires=("review",),
            effects=(),
        ),
        WorkerTask(
            task_id=f"{thread_id}:archivist{suffix}",
            thread_id=thread_id,
            worker_id="archivist",
            task_type="summarize",
            payload={
                "texts": excerpt_texts,
                "source_names": source_names,
                "source_artifact_ids": source_artifact_ids,
            },
            requires=("summarize",),
            effects=(),
        ),
        WorkerTask(
            task_id=f"{thread_id}:planner{suffix}",
            thread_id=thread_id,
            worker_id="planner",
            task_type="plan",
            payload={
                "items": plan_items,
                "objective": objective,
                "constraints": list(constraints),
            },
            requires=("plan",),
            effects=(),
        ),
        WorkerTask(
            task_id=f"{thread_id}:scribe{suffix}",
            thread_id=thread_id,
            worker_id="scribe",
            task_type="draft",
            payload={
                "title": title,
                "points": draft_points,
                "source_artifact_ids": source_artifact_ids,
            },
            requires=("draft",),
            effects=(),
        ),
    )


def _load_packet(store: FileTaskStore, artifacts: list) -> dict:
    packet_artifact = _latest_artifact(artifacts, lambda artifact: artifact.name == _PACKET_NAME)
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


def _latest_artifact(artifacts: list, predicate) -> object | None:
    matches = [artifact for artifact in artifacts if predicate(artifact)]
    if not matches:
        return None
    return max(matches, key=lambda artifact: artifact.created_at)


def _revision_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
