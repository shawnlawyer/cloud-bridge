from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from bridge.workflows.research_writing import list_research_writing
from bridge.workers.manifests import list_default_manifests
from bridge.workers.store import FileTaskStore, ReceiptRecord, TaskRecord


_WORKER_LABELS = {
    "guardian": "Steward",
    "archivist": "Archivist",
    "planner": "Planner",
    "scribe": "Scribe",
}


def build_inbox_state(store_root: str, task_limit: int = 40) -> dict:
    if not isinstance(task_limit, int) or task_limit <= 0:
        raise ValueError("task_limit must be a positive integer")

    store = FileTaskStore(store_root)
    workflows = {item["thread_id"]: item for item in list_research_writing(store_root)}
    manifests = {manifest.worker_id: manifest for manifest in list_default_manifests()}
    receipts = {receipt.receipt_id: receipt for receipt in store.list_receipts()}
    now = datetime.now(timezone.utc)

    ready_tasks = []
    blocked_tasks = []
    failed_tasks = []
    claimed_tasks = []
    recent_done = []
    thread_rows: dict[str, dict] = {}

    for record in store.list_tasks():
        entry = _task_entry(record, receipts.get(record.receipt_id), workflows, manifests, now)
        thread_row = thread_rows.setdefault(
            record.task.thread_id,
            _thread_entry(record.task.thread_id, workflows.get(record.task.thread_id)),
        )
        thread_row["task_count"] += 1
        thread_row["task_counts"][record.status] = thread_row["task_counts"].get(record.status, 0) + 1

        if record.status == "pending":
            if entry.get("blocked_reason"):
                blocked_tasks.append(entry)
                thread_row["blocked_count"] += 1
            else:
                ready_tasks.append(entry)
                thread_row["ready_count"] += 1
        elif record.status == "failed":
            failed_tasks.append(entry)
            thread_row["failed_count"] += 1
        elif record.status == "claimed":
            claimed_tasks.append(entry)
            thread_row["claimed_count"] += 1
            if entry.get("expired"):
                thread_row["expired_count"] += 1
        elif record.status == "done":
            recent_done.append(entry)

    ready_tasks.sort(key=_task_sort_key)
    blocked_tasks.sort(key=_task_sort_key)
    failed_tasks.sort(key=_task_sort_key)
    claimed_tasks.sort(key=lambda item: (0 if item.get("expired") else 1, item["thread_id"], item["worker_id"], item["task_id"]))
    recent_done.sort(key=lambda item: item["task_id"], reverse=True)

    thread_list = list(thread_rows.values())
    for item in thread_list:
        item["attention_score"] = (
            item["blocked_count"] * 100
            + item["failed_count"] * 50
            + item["expired_count"] * 20
            + item["ready_count"] * 5
            + item["claimed_count"]
        )
        item["task_counts"] = dict(sorted(item["task_counts"].items()))
    thread_list.sort(key=lambda item: (-item["attention_score"], item["title"], item["thread_id"]))

    return {
        "summary": {
            "ready_count": len(ready_tasks),
            "blocked_count": len(blocked_tasks),
            "failed_count": len(failed_tasks),
            "claimed_count": len(claimed_tasks),
            "expired_count": sum(1 for item in claimed_tasks if item.get("expired")),
            "done_count": len(recent_done),
            "thread_count": len(thread_list),
            "project_count": len(workflows),
        },
        "threads": thread_list,
        "ready_tasks": ready_tasks[:task_limit],
        "blocked_tasks": blocked_tasks[:task_limit],
        "failed_tasks": failed_tasks[:task_limit],
        "claimed_tasks": claimed_tasks[:task_limit],
        "recent_done": recent_done[:task_limit],
    }


def _task_entry(
    record: TaskRecord,
    receipt: ReceiptRecord | None,
    workflows: dict[str, dict],
    manifests: dict[str, object],
    now: datetime,
) -> dict:
    workflow = workflows.get(record.task.thread_id)
    manifest = manifests.get(record.task.worker_id)
    blocked_reason = None
    if record.status == "pending" and manifest is not None:
        admitted, blocked_reason = manifest.admits(record.task)
        if admitted:
            blocked_reason = None

    expired = bool(receipt and receipt.is_expired(now))
    return {
        "task_id": record.task.task_id,
        "thread_id": record.task.thread_id,
        "thread_title": (workflow or {}).get("title", record.task.thread_id),
        "project_url": _project_url(record.task.thread_id, workflow),
        "worker_id": record.task.worker_id,
        "worker_label": _WORKER_LABELS.get(record.task.worker_id, record.task.worker_id),
        "task_type": record.task.task_type,
        "status": record.status,
        "attempt": record.attempt,
        "max_attempts": record.max_attempts,
        "blocked_reason": blocked_reason,
        "last_error": record.last_error,
        "lease_expires_at": receipt.lease_expires_at if receipt else None,
        "expired": expired,
        "result_status": (record.result or {}).get("status"),
    }


def _thread_entry(thread_id: str, workflow: dict | None) -> dict:
    return {
        "thread_id": thread_id,
        "title": (workflow or {}).get("title", thread_id),
        "objective": (workflow or {}).get("objective", ""),
        "project_url": _project_url(thread_id, workflow),
        "task_count": 0,
        "task_counts": defaultdict(int),
        "ready_count": 0,
        "blocked_count": 0,
        "failed_count": 0,
        "claimed_count": 0,
        "expired_count": 0,
    }


def _project_url(thread_id: str, workflow: dict | None) -> str | None:
    if workflow is None:
        return None
    return f"/projects/research-writing/{thread_id}/view"


def _task_sort_key(item: dict) -> tuple:
    return (item["thread_title"], item["worker_label"], item["task_id"])
