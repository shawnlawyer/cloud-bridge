from __future__ import annotations

from dataclasses import dataclass, replace
import json
import subprocess
from urllib.parse import urlparse

from .manifests import list_default_manifests
from .store import FileTaskStore, ReceiptRecord, TaskRecord


@dataclass(frozen=True)
class CloudTransportConfig:
    bucket: str
    region: str
    queue_prefix: str

    def __post_init__(self) -> None:
        if not self.bucket:
            raise ValueError("bucket is required")
        if not self.region:
            raise ValueError("region is required")
        if not self.queue_prefix:
            raise ValueError("queue_prefix is required")


@dataclass(frozen=True)
class CloudObject:
    kind: str
    key: str
    body: dict

    def to_dict(self, bucket: str) -> dict:
        return {
            "kind": self.kind,
            "key": self.key,
            "s3_uri": f"s3://{bucket}/{self.key}",
            "body": self.body,
        }


@dataclass(frozen=True)
class QueueMessage:
    queue_name: str
    group_id: str
    dedup_id: str
    body: dict
    receipt_handle: str | None = None

    def to_dict(self) -> dict:
        data = {
            "queue_name": self.queue_name,
            "group_id": self.group_id,
            "dedup_id": self.dedup_id,
            "body": self.body,
        }
        if self.receipt_handle is not None:
            data["receipt_handle"] = self.receipt_handle
        return data


@dataclass(frozen=True)
class CloudExportPlan:
    objects: tuple[CloudObject, ...]
    messages: tuple[QueueMessage, ...]
    dead_letters: tuple[QueueMessage, ...]

    def to_dict(self, bucket: str) -> dict:
        return {
            "objects": [obj.to_dict(bucket) for obj in self.objects],
            "messages": [message.to_dict() for message in self.messages],
            "dead_letters": [message.to_dict() for message in self.dead_letters],
        }


@dataclass(frozen=True)
class _FetchedQueueBatch:
    queue_name: str
    queue_url: str
    messages: tuple[QueueMessage, ...]


class AwsCliRunner:
    def run(self, args: list[str], input_text: str | None = None) -> str:
        completed = subprocess.run(
            args,
            input=input_text,
            capture_output=True,
            check=True,
            text=True,
        )
        return completed.stdout.strip()


def build_store_export_plan(store_root: str, config: CloudTransportConfig) -> CloudExportPlan:
    store = FileTaskStore(store_root)
    objects = []
    messages = []
    dead_letters = []

    for record in store.list_tasks():
        task = record.task
        key = f"tasks/{task.worker_id}/{task.task_id.replace(':', '__')}.json"
        objects.append(CloudObject(kind="task", key=key, body=record.to_dict()))

        if record.status == "pending":
            messages.append(
                QueueMessage(
                    queue_name=f"{config.queue_prefix}-{task.worker_id}.fifo",
                    group_id=task.thread_id,
                    dedup_id=task.task_id,
                    body={
                        "task_id": task.task_id,
                        "worker_id": task.worker_id,
                        "s3_uri": f"s3://{config.bucket}/{key}",
                        "status": record.status,
                    },
                )
            )
        elif record.status == "failed":
            dead_letters.append(
                QueueMessage(
                    queue_name=f"{config.queue_prefix}-{task.worker_id}-dlq.fifo",
                    group_id=task.thread_id,
                    dedup_id=task.task_id,
                    body={
                        "task_id": task.task_id,
                        "worker_id": task.worker_id,
                        "reason": record.last_error,
                        "task": record.to_dict(),
                    },
                )
            )

    for receipt in store.list_receipts():
        key = f"receipts/{receipt.worker_id}/{receipt.receipt_id.replace(':', '__')}.json"
        objects.append(CloudObject(kind="receipt", key=key, body=receipt.to_dict()))

    return CloudExportPlan(
        objects=tuple(objects),
        messages=tuple(messages),
        dead_letters=tuple(dead_letters),
    )


def apply_store_export_plan(
    plan: CloudExportPlan,
    config: CloudTransportConfig,
    runner: AwsCliRunner | None = None,
) -> dict:
    active_runner = runner or AwsCliRunner()

    for obj in plan.objects:
        active_runner.run(
            ["aws", "s3", "cp", "-", f"s3://{config.bucket}/{obj.key}", "--region", config.region],
            input_text=json.dumps(obj.body, sort_keys=True),
        )

    for message in list(plan.messages) + list(plan.dead_letters):
        queue_url = _get_queue_url(message.queue_name, config, active_runner)
        active_runner.run(
            [
                "aws",
                "sqs",
                "send-message",
                "--queue-url",
                queue_url,
                "--message-group-id",
                message.group_id,
                "--message-deduplication-id",
                message.dedup_id,
                "--message-body",
                json.dumps(message.body, sort_keys=True),
                "--region",
                config.region,
            ]
        )

    return {
        "object_count": len(plan.objects),
        "message_count": len(plan.messages) + len(plan.dead_letters),
    }


def fetch_cloud_payload(
    config: CloudTransportConfig,
    runner: AwsCliRunner | None = None,
    worker_ids: tuple[str, ...] | list[str] | None = None,
    task_object_limit: int = 0,
    receipt_object_limit: int = 0,
    queue_message_limit: int = 2,
    include_dlq: bool = True,
) -> dict:
    payload, _ = _fetch_cloud_state(
        config,
        runner=runner,
        worker_ids=worker_ids,
        task_object_limit=task_object_limit,
        receipt_object_limit=receipt_object_limit,
        queue_message_limit=queue_message_limit,
        include_dlq=include_dlq,
    )
    return payload


def import_store_from_cloud(
    store_root: str,
    config: CloudTransportConfig,
    runner: AwsCliRunner | None = None,
    worker_ids: tuple[str, ...] | list[str] | None = None,
    task_object_limit: int = 0,
    receipt_object_limit: int = 0,
    queue_message_limit: int = 2,
    include_dlq: bool = True,
    force: bool = False,
    replay_dlq: bool = False,
    delete_fetched: bool = False,
) -> dict:
    payload, queue_batches = _fetch_cloud_state(
        config,
        runner=runner,
        worker_ids=worker_ids,
        task_object_limit=task_object_limit,
        receipt_object_limit=receipt_object_limit,
        queue_message_limit=queue_message_limit,
        include_dlq=include_dlq,
    )
    synced = sync_store_from_cloud_payload(store_root, payload, force=force)
    replayed = replay_dead_letters(store_root, payload) if replay_dlq else {"task_ids": []}
    deleted = {"message_count": 0, "queue_names": []}
    if delete_fetched:
        deleted = _delete_queue_batches(queue_batches, config, runner or AwsCliRunner())
    return {
        "fetched": payload,
        "synced": synced,
        "replayed": replayed,
        "deleted": deleted,
    }


def sync_store_from_cloud_payload(store_root: str, payload: dict, force: bool = False) -> dict:
    objects = _extract_plan_section(payload, "objects", required=False)
    task_records = []
    receipt_records = []

    for obj in objects:
        if obj.get("kind") == "task":
            task_records.append(TaskRecord.from_dict(obj["body"]))
        elif obj.get("kind") == "receipt":
            receipt_records.append(ReceiptRecord.from_dict(obj["body"]))

    for record in _extract_dead_letter_tasks(payload):
        task_records.append(record)

    return FileTaskStore(store_root).sync_records(task_records, receipt_records, force=force)


def replay_dead_letters(store_root: str, payload: dict) -> dict:
    dead_letters = _extract_plan_section(payload, "dead_letters", required=False)
    store = FileTaskStore(store_root)
    replayed = []

    for message in dead_letters:
        body = message.get("body", {})
        if not isinstance(body.get("task"), dict):
            continue
        record = TaskRecord.from_dict(body["task"])
        replay_record = replace(
            record,
            status="pending",
            attempt=0,
            claimed_by=None,
            receipt_id=None,
            last_error=None,
            result=None,
        )
        store.upsert_task_record(replay_record, force=True)
        replayed.append(replay_record.task.task_id)

    return {"task_ids": replayed}


def _fetch_cloud_state(
    config: CloudTransportConfig,
    runner: AwsCliRunner | None = None,
    worker_ids: tuple[str, ...] | list[str] | None = None,
    task_object_limit: int = 0,
    receipt_object_limit: int = 0,
    queue_message_limit: int = 2,
    include_dlq: bool = True,
) -> tuple[dict, tuple[_FetchedQueueBatch, ...]]:
    if not isinstance(task_object_limit, int) or task_object_limit < 0:
        raise ValueError("task_object_limit must be >= 0")
    if not isinstance(receipt_object_limit, int) or receipt_object_limit < 0:
        raise ValueError("receipt_object_limit must be >= 0")
    if not isinstance(queue_message_limit, int) or queue_message_limit < 0:
        raise ValueError("queue_message_limit must be >= 0")
    if not isinstance(include_dlq, bool):
        raise ValueError("include_dlq must be a boolean")

    active_runner = runner or AwsCliRunner()
    object_map: dict[str, CloudObject] = {}
    queue_batches: list[_FetchedQueueBatch] = []
    messages: list[dict] = []
    dead_letters: list[dict] = []

    for obj in _fetch_s3_objects(config, active_runner, prefix="tasks/", kind="task", limit=task_object_limit):
        object_map[obj.key] = obj
    for obj in _fetch_s3_objects(
        config,
        active_runner,
        prefix="receipts/",
        kind="receipt",
        limit=receipt_object_limit,
    ):
        object_map[obj.key] = obj

    for worker_id in _coerce_worker_ids(worker_ids):
        primary_queue = f"{config.queue_prefix}-{worker_id}.fifo"
        primary_batch = _receive_queue_batch(primary_queue, config, active_runner, queue_message_limit)
        queue_batches.append(primary_batch)
        messages.extend(message.to_dict() for message in primary_batch.messages)
        for message in primary_batch.messages:
            obj = _object_from_queue_message(config, active_runner, message)
            if obj is not None:
                object_map.setdefault(obj.key, obj)

        if include_dlq:
            dlq_name = f"{config.queue_prefix}-{worker_id}-dlq.fifo"
            dlq_batch = _receive_queue_batch(dlq_name, config, active_runner, queue_message_limit)
            queue_batches.append(dlq_batch)
            dead_letters.extend(message.to_dict() for message in dlq_batch.messages)
            for message in dlq_batch.messages:
                obj = _object_from_queue_message(config, active_runner, message)
                if obj is not None:
                    object_map.setdefault(obj.key, obj)

    payload = {
        "objects": [obj.to_dict(config.bucket) for obj in sorted(object_map.values(), key=lambda item: item.key)],
        "messages": messages,
        "dead_letters": dead_letters,
    }
    return payload, tuple(queue_batches)


def _fetch_s3_objects(
    config: CloudTransportConfig,
    runner: AwsCliRunner,
    prefix: str,
    kind: str,
    limit: int,
) -> tuple[CloudObject, ...]:
    if limit == 0:
        return ()
    raw = runner.run(
        [
            "aws",
            "s3api",
            "list-objects-v2",
            "--bucket",
            config.bucket,
            "--prefix",
            prefix,
            "--max-keys",
            str(limit),
            "--region",
            config.region,
            "--output",
            "json",
        ]
    )
    listed = json.loads(raw or "{}")
    contents = listed.get("Contents", []) or []
    objects = []
    for item in contents:
        key = item["Key"]
        body = _load_json_from_s3_key(config, runner, key)
        objects.append(CloudObject(kind=kind, key=key, body=body))
    return tuple(objects)


def _load_json_from_s3_key(config: CloudTransportConfig, runner: AwsCliRunner, key: str) -> dict:
    raw = runner.run(["aws", "s3", "cp", f"s3://{config.bucket}/{key}", "-", "--region", config.region])
    return json.loads(raw)


def _load_json_from_s3_uri(config: CloudTransportConfig, runner: AwsCliRunner, s3_uri: str) -> CloudObject:
    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise ValueError("s3_uri must point to an s3 object")
    if parsed.netloc != config.bucket:
        raise ValueError("s3_uri bucket does not match config.bucket")
    key = parsed.path.lstrip("/")
    kind = "receipt" if key.startswith("receipts/") else "task"
    return CloudObject(kind=kind, key=key, body=_load_json_from_s3_key(config, runner, key))


def _get_queue_url(queue_name: str, config: CloudTransportConfig, runner: AwsCliRunner) -> str:
    return runner.run(
        [
            "aws",
            "sqs",
            "get-queue-url",
            "--queue-name",
            queue_name,
            "--region",
            config.region,
            "--output",
            "text",
            "--query",
            "QueueUrl",
        ]
    )


def _receive_queue_batch(
    queue_name: str,
    config: CloudTransportConfig,
    runner: AwsCliRunner,
    limit: int,
) -> _FetchedQueueBatch:
    queue_url = _get_queue_url(queue_name, config, runner)
    if limit == 0:
        return _FetchedQueueBatch(queue_name=queue_name, queue_url=queue_url, messages=())

    messages = []
    remaining = limit
    while remaining > 0:
        batch_size = min(remaining, 10)
        raw = runner.run(
            [
                "aws",
                "sqs",
                "receive-message",
                "--queue-url",
                queue_url,
                "--max-number-of-messages",
                str(batch_size),
                "--visibility-timeout",
                "30",
                "--wait-time-seconds",
                "0",
                "--attribute-names",
                "All",
                "--region",
                config.region,
                "--output",
                "json",
            ]
        )
        payload = json.loads(raw or "{}")
        batch = payload.get("Messages", []) or []
        if not batch:
            break
        for index, message in enumerate(batch, start=1):
            body = json.loads(message["Body"])
            attributes = message.get("Attributes", {})
            messages.append(
                QueueMessage(
                    queue_name=queue_name,
                    group_id=attributes.get("MessageGroupId", body.get("thread_id", queue_name)),
                    dedup_id=attributes.get(
                        "MessageDeduplicationId",
                        body.get("task_id", f"{queue_name}:{len(messages) + index}"),
                    ),
                    body=body,
                    receipt_handle=message.get("ReceiptHandle"),
                )
            )
        remaining -= len(batch)
        if len(batch) < batch_size:
            break

    return _FetchedQueueBatch(queue_name=queue_name, queue_url=queue_url, messages=tuple(messages))


def _object_from_queue_message(
    config: CloudTransportConfig,
    runner: AwsCliRunner,
    message: QueueMessage,
) -> CloudObject | None:
    s3_uri = message.body.get("s3_uri")
    if isinstance(s3_uri, str) and s3_uri:
        return _load_json_from_s3_uri(config, runner, s3_uri)
    return None


def _delete_queue_batches(
    queue_batches: tuple[_FetchedQueueBatch, ...],
    config: CloudTransportConfig,
    runner: AwsCliRunner,
) -> dict:
    deleted = 0
    touched = []
    for batch in queue_batches:
        if not batch.messages:
            continue
        touched.append(batch.queue_name)
        for message in batch.messages:
            if message.receipt_handle is None:
                continue
            runner.run(
                [
                    "aws",
                    "sqs",
                    "delete-message",
                    "--queue-url",
                    batch.queue_url,
                    "--receipt-handle",
                    message.receipt_handle,
                    "--region",
                    config.region,
                ]
            )
            deleted += 1
    return {"message_count": deleted, "queue_names": touched}


def _extract_dead_letter_tasks(payload: dict) -> list[TaskRecord]:
    records = []
    for message in _extract_plan_section(payload, "dead_letters", required=False):
        body = message.get("body", {})
        if isinstance(body.get("task"), dict):
            records.append(TaskRecord.from_dict(body["task"]))
    return records


def _extract_plan_section(payload: dict, key: str, required: bool = True) -> list[dict]:
    if key in payload:
        value = payload[key]
    elif "plan" in payload and isinstance(payload["plan"], dict):
        value = payload["plan"].get(key)
    else:
        value = None

    if value is None:
        if required:
            raise ValueError(f"payload must contain {key}")
        return []
    if not isinstance(value, list):
        raise ValueError(f"payload section {key} must be a list")
    return value


def _coerce_worker_ids(worker_ids: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if worker_ids is None:
        return tuple(manifest.worker_id for manifest in list_default_manifests())
    if isinstance(worker_ids, list):
        worker_ids = tuple(worker_ids)
    if not isinstance(worker_ids, tuple) or not all(isinstance(worker_id, str) and worker_id for worker_id in worker_ids):
        raise TypeError("worker_ids must be a list or tuple of non-empty strings")
    return worker_ids
