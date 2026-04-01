from __future__ import annotations

from pathlib import Path

from .contracts import WorkerTask
from .manifests import get_default_manifest, list_default_manifests
from .runner import build_default_runner
from .store import FileTaskStore, TaskRecord


def enqueue_task(store_root: str | Path, task: WorkerTask, max_attempts: int = 3) -> TaskRecord:
    return FileTaskStore(store_root).enqueue(task, max_attempts=max_attempts)


def list_store_tasks(store_root: str | Path) -> tuple[TaskRecord, ...]:
    return FileTaskStore(store_root).list_tasks()


def list_manifests() -> tuple[dict, ...]:
    return tuple(manifest.to_dict() for manifest in list_default_manifests())


def describe_store(store_root: str | Path) -> dict:
    store = FileTaskStore(store_root)
    summary = store.summarize()
    summary["blocked"] = _list_blocked_tasks(store)
    return summary


def process_next_task(store_root: str | Path, worker_id: str) -> dict:
    store = FileTaskStore(store_root)
    reclaimed = store.reclaim_expired()
    runner = build_default_runner()
    runner.get(worker_id)
    predicate = None
    try:
        manifest = get_default_manifest(worker_id)
    except KeyError:
        manifest = None
    if manifest is not None:
        predicate = lambda record: manifest.admits(record.task)[0]

    receipt = store.claim(worker_id, predicate=predicate)
    if receipt is None:
        blocked = _list_blocked_tasks(store, worker_id=worker_id)
        return {
            "processed": False,
            "worker_id": worker_id,
            "receipt": None,
            "task": None,
            "result": None,
            "error": None,
            "reclaimed": [record.to_dict() for record in reclaimed],
            "blocked": blocked,
        }

    claimed = store.get(receipt.task_id)
    try:
        result = runner.run(claimed.task)
    except Exception as exc:
        released = store.release(receipt.receipt_id, str(exc))
        return {
            "processed": True,
            "worker_id": worker_id,
            "receipt": receipt.to_dict(),
            "task": released.to_dict(),
            "result": None,
            "error": str(exc),
            "reclaimed": [record.to_dict() for record in reclaimed],
            "blocked": [],
        }

    final_record = store.complete(receipt.receipt_id, result)
    return {
        "processed": True,
        "worker_id": worker_id,
        "receipt": receipt.to_dict(),
        "task": final_record.to_dict(),
        "result": result.to_dict(),
        "error": None,
        "reclaimed": [record.to_dict() for record in reclaimed],
        "blocked": [],
    }


def dispatch_tasks(store_root: str | Path, limit: int = 1) -> dict:
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    store = FileTaskStore(store_root)
    reclaimed = store.reclaim_expired()
    results = []
    processed = 0
    manifests = sorted(
        list_default_manifests(),
        key=lambda manifest: (
            manifest.dispatch_policy.priority,
            manifest.worker_id,
        ),
    )

    while processed < limit:
        progressed = False
        for manifest in manifests:
            claims = 0
            while claims < manifest.dispatch_policy.max_claims_per_cycle and processed < limit:
                out = process_next_task(store_root, manifest.worker_id)
                if not out["processed"]:
                    break
                out["reclaimed"] = []
                results.append(out)
                processed += 1
                claims += 1
                progressed = True
        if not progressed:
            break

    return {
        "processed_count": processed,
        "reclaimed_count": len(reclaimed),
        "reclaimed": [record.to_dict() for record in reclaimed],
        "blocked": _list_blocked_tasks(FileTaskStore(store_root)),
        "results": results,
    }


def _list_blocked_tasks(store: FileTaskStore, worker_id: str | None = None) -> list[dict]:
    manifests = {manifest.worker_id: manifest for manifest in list_default_manifests()}
    blocked = []
    for record in store.list_tasks():
        if record.status != "pending":
            continue
        if worker_id is not None and record.task.worker_id != worker_id:
            continue
        manifest = manifests.get(record.task.worker_id)
        if manifest is None:
            continue
        admitted, reason = manifest.admits(record.task)
        if admitted:
            continue
        blocked.append(
            {
                "task_id": record.task.task_id,
                "worker_id": record.task.worker_id,
                "task_type": record.task.task_type,
                "reason": reason,
            }
        )
    return blocked
