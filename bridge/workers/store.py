from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path

from .contracts import WorkerResult, WorkerTask
from .runner import LocalWorkerRunner

_TASK_STATUS_VALUES = frozenset({"pending", "claimed", "done", "failed"})
_RECEIPT_STATUS_VALUES = frozenset({"open", "completed", "released"})


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, sort_keys=True) + "\n")


@dataclass(frozen=True)
class TaskRecord:
    task: WorkerTask
    status: str
    attempt: int
    max_attempts: int
    claimed_by: str | None = None
    receipt_id: str | None = None
    last_error: str | None = None
    result: dict | None = None

    def __post_init__(self) -> None:
        if self.status not in _TASK_STATUS_VALUES:
            raise ValueError(f"Unsupported task status: {self.status}")
        if not isinstance(self.attempt, int) or self.attempt < 0:
            raise ValueError("attempt must be >= 0")
        if not isinstance(self.max_attempts, int) or self.max_attempts <= 0:
            raise ValueError("max_attempts must be > 0")
        if self.result is not None and not isinstance(self.result, dict):
            raise TypeError("result must be a dict or None")

    def to_dict(self) -> dict:
        return {
            "task": self.task.to_dict(),
            "status": self.status,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "claimed_by": self.claimed_by,
            "receipt_id": self.receipt_id,
            "last_error": self.last_error,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskRecord":
        return cls(
            task=WorkerTask(**data["task"]),
            status=data["status"],
            attempt=data["attempt"],
            max_attempts=data["max_attempts"],
            claimed_by=data.get("claimed_by"),
            receipt_id=data.get("receipt_id"),
            last_error=data.get("last_error"),
            result=data.get("result"),
        )


@dataclass(frozen=True)
class ReceiptRecord:
    receipt_id: str
    task_id: str
    worker_id: str
    attempt: int
    status: str

    def __post_init__(self) -> None:
        if self.status not in _RECEIPT_STATUS_VALUES:
            raise ValueError(f"Unsupported receipt status: {self.status}")
        if not isinstance(self.attempt, int) or self.attempt <= 0:
            raise ValueError("attempt must be > 0")

    def to_dict(self) -> dict:
        return {
            "receipt_id": self.receipt_id,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "attempt": self.attempt,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReceiptRecord":
        return cls(
            receipt_id=data["receipt_id"],
            task_id=data["task_id"],
            worker_id=data["worker_id"],
            attempt=data["attempt"],
            status=data["status"],
        )


class FileTaskStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.tasks_dir = self.root / "tasks"
        self.receipts_dir = self.root / "receipts"
        self.events_path = self.root / "events.jsonl"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.events_path.touch(exist_ok=True)

    def enqueue(self, task: WorkerTask, max_attempts: int = 3) -> TaskRecord:
        record = TaskRecord(task=task, status="pending", attempt=0, max_attempts=max_attempts)
        path = self._task_path(task.task_id)
        if path.exists():
            raise ValueError("Task already exists")
        self._write_task(record)
        _append_jsonl(
            self.events_path,
            {"event": "enqueued", "task_id": task.task_id, "worker_id": task.worker_id},
        )
        return record

    def claim(self, worker_id: str) -> ReceiptRecord | None:
        candidates = [
            record
            for record in self.list_tasks()
            if record.status == "pending" and record.task.worker_id == worker_id
        ]
        if not candidates:
            return None

        record = candidates[0]
        attempt = record.attempt + 1
        receipt = ReceiptRecord(
            receipt_id=f"rcpt:{record.task.task_id}:{attempt}",
            task_id=record.task.task_id,
            worker_id=worker_id,
            attempt=attempt,
            status="open",
        )
        updated = replace(
            record,
            status="claimed",
            attempt=attempt,
            claimed_by=worker_id,
            receipt_id=receipt.receipt_id,
        )
        self._write_task(updated)
        self._write_receipt(receipt)
        _append_jsonl(
            self.events_path,
            {
                "event": "claimed",
                "task_id": record.task.task_id,
                "worker_id": worker_id,
                "receipt_id": receipt.receipt_id,
                "attempt": attempt,
            },
        )
        return receipt

    def complete(self, receipt_id: str, result: WorkerResult) -> TaskRecord:
        receipt = self._load_receipt(receipt_id)
        if receipt.status != "open":
            raise RuntimeError("Receipt is not open")

        record = self.get(receipt.task_id)
        if record.receipt_id != receipt_id:
            raise RuntimeError("Receipt does not match current task claim")
        if result.task_id != record.task.task_id:
            raise ValueError("result.task_id must match receipt.task_id")
        if result.worker_id != receipt.worker_id:
            raise ValueError("result.worker_id must match receipt.worker_id")

        updated = replace(
            record,
            status="done",
            result=result.to_dict(),
            last_error=None,
        )
        closed_receipt = replace(receipt, status="completed")
        self._write_task(updated)
        self._write_receipt(closed_receipt)
        _append_jsonl(
            self.events_path,
            {
                "event": "completed",
                "task_id": record.task.task_id,
                "worker_id": receipt.worker_id,
                "receipt_id": receipt_id,
                "result_status": result.status,
            },
        )
        return updated

    def release(self, receipt_id: str, reason: str) -> TaskRecord:
        receipt = self._load_receipt(receipt_id)
        if receipt.status != "open":
            raise RuntimeError("Receipt is not open")

        record = self.get(receipt.task_id)
        if record.receipt_id != receipt_id:
            raise RuntimeError("Receipt does not match current task claim")

        failed = record.attempt >= record.max_attempts
        updated = replace(
            record,
            status="failed" if failed else "pending",
            claimed_by=None,
            receipt_id=None,
            last_error=reason,
        )
        closed_receipt = replace(receipt, status="released")
        self._write_task(updated)
        self._write_receipt(closed_receipt)
        _append_jsonl(
            self.events_path,
            {
                "event": "failed" if failed else "released",
                "task_id": record.task.task_id,
                "worker_id": receipt.worker_id,
                "receipt_id": receipt_id,
                "reason": reason,
                "attempt": record.attempt,
            },
        )
        return updated

    def get(self, task_id: str) -> TaskRecord:
        path = self._task_path(task_id)
        if not path.exists():
            raise KeyError("Unknown task")
        return TaskRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_tasks(self) -> tuple[TaskRecord, ...]:
        records = []
        for path in sorted(self.tasks_dir.glob("*.json")):
            records.append(TaskRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return tuple(records)

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id.replace(':', '__')}.json"

    def _receipt_path(self, receipt_id: str) -> Path:
        return self.receipts_dir / f"{receipt_id.replace(':', '__')}.json"

    def _load_receipt(self, receipt_id: str) -> ReceiptRecord:
        path = self._receipt_path(receipt_id)
        if not path.exists():
            raise KeyError("Unknown receipt")
        return ReceiptRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def _write_task(self, record: TaskRecord) -> None:
        _write_json(self._task_path(record.task.task_id), record.to_dict())

    def _write_receipt(self, receipt: ReceiptRecord) -> None:
        _write_json(self._receipt_path(receipt.receipt_id), receipt.to_dict())


def run_next_task(store: FileTaskStore, runner: LocalWorkerRunner, worker_id: str) -> WorkerResult | None:
    receipt = store.claim(worker_id)
    if receipt is None:
        return None

    record = store.get(receipt.task_id)
    try:
        result = runner.run(record.task)
    except Exception as exc:
        store.release(receipt.receipt_id, str(exc))
        raise

    store.complete(receipt.receipt_id, result)
    return result
