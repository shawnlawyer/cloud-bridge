from __future__ import annotations

import json
from pathlib import Path
import re

from bridge.workflows import (
    bootstrap_research_writing,
    collect_research_writing_sources,
    refresh_research_writing,
)


def register_drop_folder(
    store_root: str | Path,
    *,
    name: str,
    folder_path: str | Path,
    title: str,
    objective: str,
    constraints: list[str] | tuple[str, ...] = (),
    thread_id: str | None = None,
    max_attempts: int = 3,
    max_files: int = 64,
    max_bytes: int = 1_000_000,
) -> dict:
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")
    if not isinstance(title, str) or not title:
        raise ValueError("title must be a non-empty string")
    if not isinstance(objective, str) or not objective:
        raise ValueError("objective must be a non-empty string")
    if not isinstance(constraints, (list, tuple)) or not all(isinstance(item, str) and item for item in constraints):
        raise ValueError("constraints must be a list or tuple of non-empty strings")
    if thread_id is not None and (not isinstance(thread_id, str) or not thread_id):
        raise ValueError("thread_id must be a non-empty string when provided")
    if not isinstance(max_attempts, int) or max_attempts <= 0:
        raise ValueError("max_attempts must be a positive integer")
    if not isinstance(max_files, int) or max_files <= 0:
        raise ValueError("max_files must be a positive integer")
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")

    folder = Path(folder_path).expanduser()
    if not folder.exists() or not folder.is_dir():
        raise ValueError("folder_path must point to an existing directory")

    path = _registration_path(store_root, name)
    if path.exists():
        raise ValueError("drop folder already registered")

    registration = {
        "name": name,
        "folder_path": str(folder.resolve()),
        "title": title,
        "objective": objective,
        "constraints": list(constraints),
        "thread_id": thread_id or f"research:drop:{_slug(name)}",
        "max_attempts": max_attempts,
        "max_files": max_files,
        "max_bytes": max_bytes,
        "created_at": _utc_now_text(),
        "last_scan_at": None,
        "last_import_at": None,
        "source_state": {},
    }
    _write_registration(path, registration)
    return _registration_summary(Path(store_root), registration)


def list_drop_folders(store_root: str | Path) -> list[dict]:
    root = Path(store_root)
    items = []
    for path in sorted(_registry_dir(root).glob("*.json")):
        registration = _read_registration(path)
        items.append(_registration_summary(root, registration))
    return items


def scan_drop_folders(store_root: str | Path, *, name: str | None = None) -> dict:
    root = Path(store_root)
    if name is None:
        registration_paths = sorted(_registry_dir(root).glob("*.json"))
    else:
        registration_paths = [_registration_path(root, name)]
        if not registration_paths[0].exists():
            raise ValueError("drop folder is not registered")

    results = []
    imported_count = 0
    refreshed_count = 0
    unchanged_count = 0
    error_count = 0
    for path in registration_paths:
        registration = _read_registration(path)
        try:
            result = _scan_registration(root, registration)
            _write_registration(path, result["registration"])
            item = result["result"]
            if item["status"] == "imported":
                imported_count += 1
            elif item["status"] == "refreshed":
                refreshed_count += 1
            elif item["status"] in {"unchanged", "empty", "missing"}:
                unchanged_count += 1
        except Exception as exc:  # pragma: no cover - defensive boundary for UI/CLI
            item = {
                "name": registration["name"],
                "thread_id": registration["thread_id"],
                "project_url": _project_url(registration["thread_id"]),
                "status": "error",
                "error": str(exc),
            }
            error_count += 1
        results.append(item)

    return {
        "drop_folders": results,
        "summary": {
            "count": len(results),
            "imported_count": imported_count,
            "refreshed_count": refreshed_count,
            "unchanged_count": unchanged_count,
            "error_count": error_count,
        },
        "imported_count": imported_count,
        "refreshed_count": refreshed_count,
        "unchanged_count": unchanged_count,
        "error_count": error_count,
    }


def _scan_registration(store_root: Path, registration: dict) -> dict:
    folder = Path(registration["folder_path"])
    base_result = {
        "name": registration["name"],
        "thread_id": registration["thread_id"],
        "project_url": _project_url(registration["thread_id"]),
        "folder_path": registration["folder_path"],
        "title": registration["title"],
    }
    registration["last_scan_at"] = _utc_now_text()

    if not folder.exists() or not folder.is_dir():
        return {
            "registration": registration,
            "result": {**base_result, "status": "missing", "error": "folder is not available"},
        }

    collected = collect_research_writing_sources(
        folder,
        max_files=registration.get("max_files", 64),
        max_bytes=registration.get("max_bytes", 1_000_000),
    )
    current_state = _build_source_state(folder, collected["source_paths"])
    previous_state = registration.get("source_state", {})
    changed_paths, removed_paths = _diff_source_state(previous_state, current_state)

    result = {
        **base_result,
        "source_count": len(current_state),
        "changed_paths": changed_paths,
        "removed_paths": removed_paths,
        "skipped": collected["skipped"],
        "status": "unchanged",
    }

    if not previous_state:
        if not collected["source_paths"]:
            result["status"] = "empty"
            return {"registration": registration, "result": result}
        workflow = bootstrap_research_writing(
            store_root,
            title=registration["title"],
            objective=registration["objective"],
            source_paths=collected["source_paths"],
            constraints=registration.get("constraints", []),
            thread_id=registration["thread_id"],
            max_attempts=registration.get("max_attempts", 3),
        )
        result.update({"status": "imported", "workflow": workflow})
    elif changed_paths or removed_paths:
        workflow = refresh_research_writing(
            store_root,
            thread_id=registration["thread_id"],
            source_paths=collected["source_paths"],
            title=registration["title"],
            objective=registration["objective"],
            constraints=registration.get("constraints", []),
            max_attempts=registration.get("max_attempts", 3),
        )
        result.update({"status": "refreshed", "workflow": workflow})

    if result["status"] in {"imported", "refreshed"}:
        registration["last_import_at"] = _utc_now_text()
        registration["source_state"] = current_state
    elif not previous_state:
        registration["source_state"] = current_state

    return {"registration": registration, "result": result}


def _registration_summary(store_root: Path, registration: dict) -> dict:
    folder = Path(registration["folder_path"])
    current_state = {}
    skipped = []
    exists = folder.exists() and folder.is_dir()
    if exists:
        collected = collect_research_writing_sources(
            folder,
            max_files=registration.get("max_files", 64),
            max_bytes=registration.get("max_bytes", 1_000_000),
        )
        current_state = _build_source_state(folder, collected["source_paths"])
        skipped = collected["skipped"]
    previous_state = registration.get("source_state", {})
    changed_paths, removed_paths = _diff_source_state(previous_state, current_state)
    return {
        "name": registration["name"],
        "folder_path": registration["folder_path"],
        "title": registration["title"],
        "objective": registration["objective"],
        "constraints": list(registration.get("constraints", [])),
        "thread_id": registration["thread_id"],
        "project_url": _project_url(registration["thread_id"]),
        "created_at": registration.get("created_at"),
        "last_scan_at": registration.get("last_scan_at"),
        "last_import_at": registration.get("last_import_at"),
        "max_attempts": registration.get("max_attempts", 3),
        "max_files": registration.get("max_files", 64),
        "max_bytes": registration.get("max_bytes", 1_000_000),
        "exists": exists,
        "source_count": len(current_state),
        "tracked_source_count": len(previous_state),
        "pending_change_count": len(changed_paths) + len(removed_paths),
        "changed_paths": changed_paths,
        "removed_paths": removed_paths,
        "skipped_count": len(skipped),
        "skipped": skipped,
    }


def _registration_path(store_root: str | Path, name: str) -> Path:
    return _registry_dir(Path(store_root)) / f"{_slug(name)}.json"


def _registry_dir(store_root: Path) -> Path:
    path = store_root / "drop_folders" / "registrations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_registration(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_registration(path: Path, registration: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registration, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_source_state(root: Path, source_paths: list[str]) -> dict[str, dict]:
    state = {}
    for raw_path in source_paths:
        path = Path(raw_path)
        stat = path.stat()
        relative = str(path.relative_to(root))
        state[relative] = {
            "path": str(path),
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    return state


def _diff_source_state(previous: dict[str, dict], current: dict[str, dict]) -> tuple[list[str], list[str]]:
    changed = sorted(
        relative
        for relative, current_item in current.items()
        if relative not in previous or previous.get(relative) != current_item
    )
    removed = sorted(relative for relative in previous if relative not in current)
    return changed, removed


def _project_url(thread_id: str) -> str:
    return f"/projects/research-writing/{thread_id}/view"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48] or "drop-folder"


def _utc_now_text() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
