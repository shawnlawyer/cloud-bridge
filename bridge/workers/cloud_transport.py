from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess

from .store import FileTaskStore


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

    def to_dict(self) -> dict:
        return {
            "queue_name": self.queue_name,
            "group_id": self.group_id,
            "dedup_id": self.dedup_id,
            "body": self.body,
        }


@dataclass(frozen=True)
class CloudExportPlan:
    objects: tuple[CloudObject, ...]
    messages: tuple[QueueMessage, ...]

    def to_dict(self, bucket: str) -> dict:
        return {
            "objects": [obj.to_dict(bucket) for obj in self.objects],
            "messages": [message.to_dict() for message in self.messages],
        }


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

    for receipt in store.list_receipts():
        key = f"receipts/{receipt.worker_id}/{receipt.receipt_id.replace(':', '__')}.json"
        objects.append(CloudObject(kind="receipt", key=key, body=receipt.to_dict()))

    return CloudExportPlan(objects=tuple(objects), messages=tuple(messages))


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

    for message in plan.messages:
        queue_url = active_runner.run(
            [
                "aws",
                "sqs",
                "get-queue-url",
                "--queue-name",
                message.queue_name,
                "--region",
                config.region,
                "--output",
                "text",
                "--query",
                "QueueUrl",
            ]
        )
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
        "message_count": len(plan.messages),
    }
