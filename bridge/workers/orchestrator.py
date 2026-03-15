from __future__ import annotations

from pathlib import Path

from .contracts import WorkerTask
from .manifests import list_default_manifests
from .runner import build_default_runner
from .store import FileTaskStore, TaskRecord


def enqueue_task(store_root: str | Path, task: WorkerTask, max_attempts: int = 3) -> TaskRecord:
    return FileTaskStore(store_root).enqueue(task, max_attempts=max_attempts)


def list_store_tasks(store_root: str | Path) -> tuple[TaskRecord, ...]:
    return FileTaskStore(store_root).list_tasks()


def list_manifests() -> tuple[dict, ...]:
    return tuple(manifest.to_dict() for manifest in list_default_manifests())


def process_next_task(store_root: str | Path, worker_id: str) -> dict:
    store = FileTaskStore(store_root)
    runner = build_default_runner()
    runner.get(worker_id)

    receipt = store.claim(worker_id)
    if receipt is None:
        return {
            "processed": False,
            "worker_id": worker_id,
            "receipt": None,
            "task": None,
            "result": None,
            "error": None,
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
        }

    final_record = store.complete(receipt.receipt_id, result)
    return {
        "processed": True,
        "worker_id": worker_id,
        "receipt": receipt.to_dict(),
        "task": final_record.to_dict(),
        "result": result.to_dict(),
        "error": None,
    }


def dispatch_tasks(store_root: str | Path, limit: int = 1) -> dict:
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

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
                results.append(out)
                processed += 1
                claims += 1
                progressed = True
        if not progressed:
            break

    return {
        "processed_count": processed,
        "results": results,
    }
