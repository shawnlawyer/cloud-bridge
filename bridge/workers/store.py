from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
import shutil

from .contracts import WorkerResult, WorkerTask
from .runner import LocalWorkerRunner

_TASK_STATUS_VALUES = frozenset({"pending", "claimed", "done", "failed"})
_RECEIPT_STATUS_VALUES = frozenset({"open", "completed", "released"})
_TASK_STATUS_PRIORITY = {"pending": 0, "claimed": 1, "done": 2, "failed": 2}
_RECEIPT_STATUS_PRIORITY = {"open": 0, "completed": 1, "released": 1}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, sort_keys=True) + "\n")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


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
    lease_expires_at: str | None = None

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
            "lease_expires_at": self.lease_expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReceiptRecord":
        return cls(
            receipt_id=data["receipt_id"],
            task_id=data["task_id"],
            worker_id=data["worker_id"],
            attempt=data["attempt"],
            status=data["status"],
            lease_expires_at=data.get("lease_expires_at"),
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.status != "open" or self.lease_expires_at is None:
            return False
        return _parse_utc(self.lease_expires_at) <= (now or _utc_now())


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    owner_id: str
    name: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: str
    path: str

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "owner_id": self.owner_id,
            "name": self.name,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "created_at": self.created_at,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ArtifactRecord":
        return cls(
            artifact_id=data["artifact_id"],
            owner_id=data["owner_id"],
            name=data["name"],
            media_type=data["media_type"],
            size_bytes=data["size_bytes"],
            sha256=data["sha256"],
            created_at=data["created_at"],
            path=data["path"],
        )


class FileTaskStore:
    def __init__(self, root: str | Path, lease_seconds: int = 300) -> None:
        if not isinstance(lease_seconds, int) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be a positive integer")
        self.root = Path(root)
        self.lease_seconds = lease_seconds
        self.tasks_dir = self.root / "tasks"
        self.receipts_dir = self.root / "receipts"
        self.artifacts_dir = self.root / "artifacts"
        self.artifact_files_dir = self.artifacts_dir / "files"
        self.artifact_meta_dir = self.artifacts_dir / "meta"
        self.events_path = self.root / "events.jsonl"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_files_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_meta_dir.mkdir(parents=True, exist_ok=True)
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

    def claim(
        self,
        worker_id: str,
        predicate: Callable[[TaskRecord], bool] | None = None,
        now: datetime | None = None,
        lease_seconds: int | None = None,
    ) -> ReceiptRecord | None:
        active_now = now or _utc_now()
        active_lease_seconds = self.lease_seconds if lease_seconds is None else lease_seconds
        if not isinstance(active_lease_seconds, int) or active_lease_seconds <= 0:
            raise ValueError("lease_seconds must be a positive integer")

        candidates = [
            record
            for record in self.list_tasks()
            if record.status == "pending"
            and record.task.worker_id == worker_id
            and (predicate is None or predicate(record))
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
            lease_expires_at=_format_utc(active_now + timedelta(seconds=active_lease_seconds)),
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

    def reclaim_expired(self, now: datetime | None = None) -> tuple[TaskRecord, ...]:
        active_now = now or _utc_now()
        reclaimed = []
        for receipt in self.list_receipts():
            if not receipt.is_expired(active_now):
                continue
            try:
                record = self.get(receipt.task_id)
            except KeyError:
                continue
            if record.status != "claimed" or record.receipt_id != receipt.receipt_id:
                continue
            updated = self.release(receipt.receipt_id, "lease expired")
            reclaimed.append(updated)
            _append_jsonl(
                self.events_path,
                {
                    "event": "reclaimed",
                    "task_id": updated.task.task_id,
                    "worker_id": receipt.worker_id,
                    "receipt_id": receipt.receipt_id,
                    "status": updated.status,
                },
            )
        return tuple(reclaimed)

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

    def list_receipts(self) -> tuple[ReceiptRecord, ...]:
        records = []
        for path in sorted(self.receipts_dir.glob("*.json")):
            records.append(ReceiptRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return tuple(records)

    def write_artifact(
        self,
        owner_id: str,
        name: str,
        content: str,
        media_type: str = "text/plain",
    ) -> ArtifactRecord:
        if not isinstance(owner_id, str) or not owner_id:
            raise ValueError("owner_id must be a non-empty string")
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        if not isinstance(content, str):
            raise TypeError("content must be a string")
        if not isinstance(media_type, str) or not media_type:
            raise ValueError("media_type must be a non-empty string")

        artifact_id = self._build_artifact_id(owner_id, name)
        file_path = self.artifact_files_dir / f"{artifact_id}__{_safe_name(name)}"
        file_path.write_text(content, encoding="utf-8")
        record = self._artifact_record(owner_id, name, media_type, file_path)
        self._write_artifact(record)
        _append_jsonl(
            self.events_path,
            {"event": "artifact_written", "artifact_id": record.artifact_id, "owner_id": owner_id},
        )
        return record

    def copy_artifact(
        self,
        owner_id: str,
        source_path: str | Path,
        name: str | None = None,
        media_type: str | None = None,
    ) -> ArtifactRecord:
        if not isinstance(owner_id, str) or not owner_id:
            raise ValueError("owner_id must be a non-empty string")
        source = Path(source_path)
        if not source.exists() or not source.is_file():
            raise ValueError("source_path must point to an existing file")
        artifact_name = name or source.name
        guessed_media_type = media_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream"

        artifact_id = self._build_artifact_id(owner_id, artifact_name)
        file_path = self.artifact_files_dir / f"{artifact_id}__{_safe_name(artifact_name)}"
        shutil.copy2(source, file_path)
        record = self._artifact_record(owner_id, artifact_name, guessed_media_type, file_path)
        self._write_artifact(record)
        _append_jsonl(
            self.events_path,
            {"event": "artifact_copied", "artifact_id": record.artifact_id, "owner_id": owner_id},
        )
        return record

    def list_artifacts(self, owner_id: str | None = None) -> tuple[ArtifactRecord, ...]:
        records = []
        for path in sorted(self.artifact_meta_dir.glob("*.json")):
            record = ArtifactRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if owner_id is not None and record.owner_id != owner_id:
                continue
            records.append(record)
        return tuple(records)

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        path = self._artifact_meta_path(artifact_id)
        if not path.exists():
            raise KeyError("Unknown artifact")
        return ArtifactRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def read_artifact_text(self, artifact_id: str) -> str:
        record = self.get_artifact(artifact_id)
        return Path(record.path).read_text(encoding="utf-8")

    def upsert_task_record(self, record: TaskRecord, force: bool = False) -> TaskRecord:
        path = self._task_path(record.task.task_id)
        if not path.exists():
            self._write_task(record)
            _append_jsonl(self.events_path, {"event": "task_synced", "task_id": record.task.task_id})
            return record

        existing = self.get(record.task.task_id)
        if not force and not _incoming_task_wins(existing, record):
            return existing

        self._write_task(record)
        _append_jsonl(self.events_path, {"event": "task_synced", "task_id": record.task.task_id})
        return record

    def upsert_receipt_record(self, receipt: ReceiptRecord, force: bool = False) -> ReceiptRecord:
        path = self._receipt_path(receipt.receipt_id)
        if not path.exists():
            self._write_receipt(receipt)
            _append_jsonl(self.events_path, {"event": "receipt_synced", "receipt_id": receipt.receipt_id})
            return receipt

        existing = self._load_receipt(receipt.receipt_id)
        if not force and not _incoming_receipt_wins(existing, receipt):
            return existing

        self._write_receipt(receipt)
        _append_jsonl(self.events_path, {"event": "receipt_synced", "receipt_id": receipt.receipt_id})
        return receipt

    def sync_records(
        self,
        task_records: tuple[TaskRecord, ...] | list[TaskRecord] = (),
        receipt_records: tuple[ReceiptRecord, ...] | list[ReceiptRecord] = (),
        force: bool = False,
    ) -> dict:
        synced_tasks = [self.upsert_task_record(record, force=force).task.task_id for record in task_records]
        synced_receipts = [
            self.upsert_receipt_record(receipt, force=force).receipt_id for receipt in receipt_records
        ]
        return {
            "task_ids": synced_tasks,
            "receipt_ids": synced_receipts,
        }

    def summarize(self, now: datetime | None = None) -> dict:
        active_now = now or _utc_now()
        task_counts = {status: 0 for status in sorted(_TASK_STATUS_VALUES)}
        receipt_counts = {status: 0 for status in sorted(_RECEIPT_STATUS_VALUES)}
        expired_receipts = []

        tasks = self.list_tasks()
        receipts = self.list_receipts()
        artifacts = self.list_artifacts()
        for record in tasks:
            task_counts[record.status] += 1
        for receipt in receipts:
            receipt_counts[receipt.status] += 1
            if receipt.is_expired(active_now):
                expired_receipts.append(receipt.receipt_id)

        event_count = 0
        if self.events_path.exists():
            with self.events_path.open("r", encoding="utf-8") as handle:
                event_count = sum(1 for _ in handle)

        return {
            "task_count": len(tasks),
            "task_counts": task_counts,
            "receipt_count": len(receipts),
            "receipt_counts": receipt_counts,
            "artifact_count": len(artifacts),
            "expired_receipt_ids": expired_receipts,
            "event_count": event_count,
        }

    def recent_events(self, limit: int = 20) -> list[dict]:
        if not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be >= 0")
        if limit == 0 or not self.events_path.exists():
            return []
        with self.events_path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        return [json.loads(line) for line in lines[-limit:] if line.strip()]

    def prune(self, keep_done: int = 100, keep_failed: int = 50, event_keep: int = 1000) -> dict:
        for name, value in (("keep_done", keep_done), ("keep_failed", keep_failed), ("event_keep", event_keep)):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be >= 0")

        deleted_task_ids = []
        deleted_receipt_ids = []
        deleted_artifact_ids = []

        deleted_task_ids.extend(self._prune_task_status("done", keep_done))
        deleted_task_ids.extend(self._prune_task_status("failed", keep_failed))

        deleted_receipt_ids.extend(self._delete_receipts_for_tasks(set(deleted_task_ids)))
        deleted_artifact_ids.extend(self._delete_artifacts_for_owners(set(deleted_task_ids)))
        event_count = self._compact_events(event_keep)

        return {
            "deleted_task_ids": deleted_task_ids,
            "deleted_receipt_ids": deleted_receipt_ids,
            "deleted_artifact_ids": deleted_artifact_ids,
            "event_count": event_count,
        }

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id.replace(':', '__')}.json"

    def _receipt_path(self, receipt_id: str) -> Path:
        return self.receipts_dir / f"{receipt_id.replace(':', '__')}.json"

    def _artifact_meta_path(self, artifact_id: str) -> Path:
        return self.artifact_meta_dir / f"{artifact_id.replace(':', '__')}.json"

    def _load_receipt(self, receipt_id: str) -> ReceiptRecord:
        path = self._receipt_path(receipt_id)
        if not path.exists():
            raise KeyError("Unknown receipt")
        return ReceiptRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def _write_task(self, record: TaskRecord) -> None:
        _write_json(self._task_path(record.task.task_id), record.to_dict())

    def _write_receipt(self, receipt: ReceiptRecord) -> None:
        _write_json(self._receipt_path(receipt.receipt_id), receipt.to_dict())

    def _write_artifact(self, record: ArtifactRecord) -> None:
        _write_json(self._artifact_meta_path(record.artifact_id), record.to_dict())

    def _artifact_record(self, owner_id: str, name: str, media_type: str, file_path: Path) -> ArtifactRecord:
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        return ArtifactRecord(
            artifact_id=file_path.name.split("__", 1)[0],
            owner_id=owner_id,
            name=name,
            media_type=media_type,
            size_bytes=file_path.stat().st_size,
            sha256=digest,
            created_at=_format_utc(_utc_now()),
            path=str(file_path),
        )

    def _build_artifact_id(self, owner_id: str, name: str) -> str:
        digest = hashlib.sha256(f"{owner_id}:{name}:{_utc_now().isoformat()}".encode("utf-8")).hexdigest()[:12]
        return f"artifact:{digest}"

    def _prune_task_status(self, status: str, keep: int) -> list[str]:
        matches = []
        for path in self.tasks_dir.glob("*.json"):
            record = TaskRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if record.status == status:
                matches.append((path.stat().st_mtime_ns, record, path))
        matches.sort(key=lambda item: item[0], reverse=True)

        deleted = []
        for _, record, path in matches[keep:]:
            path.unlink(missing_ok=True)
            deleted.append(record.task.task_id)
            _append_jsonl(
                self.events_path,
                {"event": "pruned_task", "task_id": record.task.task_id, "status": record.status},
            )
        return deleted

    def _delete_receipts_for_tasks(self, task_ids: set[str]) -> list[str]:
        if not task_ids:
            return []
        deleted = []
        for path in self.receipts_dir.glob("*.json"):
            receipt = ReceiptRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if receipt.task_id not in task_ids:
                continue
            path.unlink(missing_ok=True)
            deleted.append(receipt.receipt_id)
            _append_jsonl(
                self.events_path,
                {"event": "pruned_receipt", "receipt_id": receipt.receipt_id, "task_id": receipt.task_id},
            )
        return deleted

    def _delete_artifacts_for_owners(self, owner_ids: set[str]) -> list[str]:
        if not owner_ids:
            return []
        deleted = []
        for path in self.artifact_meta_dir.glob("*.json"):
            record = ArtifactRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if record.owner_id not in owner_ids:
                continue
            artifact_path = Path(record.path)
            artifact_path.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            deleted.append(record.artifact_id)
            _append_jsonl(
                self.events_path,
                {"event": "pruned_artifact", "artifact_id": record.artifact_id, "owner_id": record.owner_id},
            )
        return deleted

    def _compact_events(self, keep: int) -> int:
        if not self.events_path.exists():
            return 0

        with self.events_path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        kept_lines = lines[-keep:] if keep else []
        self.events_path.write_text("".join(kept_lines), encoding="utf-8")
        return len(kept_lines)


def run_next_task(store: FileTaskStore, runner: LocalWorkerRunner, worker_id: str) -> WorkerResult | None:
    store.reclaim_expired()
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


def _incoming_task_wins(existing: TaskRecord, incoming: TaskRecord) -> bool:
    existing_key = (
        existing.attempt,
        _TASK_STATUS_PRIORITY[existing.status],
        1 if existing.result is not None else 0,
        1 if existing.last_error else 0,
    )
    incoming_key = (
        incoming.attempt,
        _TASK_STATUS_PRIORITY[incoming.status],
        1 if incoming.result is not None else 0,
        1 if incoming.last_error else 0,
    )
    return incoming_key > existing_key


def _incoming_receipt_wins(existing: ReceiptRecord, incoming: ReceiptRecord) -> bool:
    existing_key = (
        existing.attempt,
        _RECEIPT_STATUS_PRIORITY[existing.status],
        existing.lease_expires_at or "",
    )
    incoming_key = (
        incoming.attempt,
        _RECEIPT_STATUS_PRIORITY[incoming.status],
        incoming.lease_expires_at or "",
    )
    return incoming_key > existing_key


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
