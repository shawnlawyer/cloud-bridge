import json
import subprocess
import tempfile
import unittest
from unittest import mock

from bridge.workers import FileTaskStore, WorkerTask, build_default_runner, run_next_task
from bridge.workers.cloud_transport import (
    AwsCliRunner,
    CloudTransportConfig,
    apply_store_export_plan,
    build_store_export_plan,
    fetch_cloud_payload,
    import_store_from_cloud,
    replay_dead_letters,
    sync_store_from_cloud_payload,
)


class FakeAwsCliRunner(AwsCliRunner):
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self.s3_objects: dict[str, dict] = {}
        self.queue_messages: dict[str, list[dict]] = {}

    def run(self, args: list[str], input_text: str | None = None) -> str:
        self.calls.append((args, input_text))
        if args[:3] == ["aws", "sqs", "get-queue-url"]:
            queue_name = args[args.index("--queue-name") + 1]
            return f"https://example.com/queue/{queue_name}"
        if args[:3] == ["aws", "sqs", "send-message"]:
            return ""
        if args[:3] == ["aws", "sqs", "delete-message"]:
            return ""
        if args[:3] == ["aws", "sqs", "receive-message"]:
            queue_url = args[args.index("--queue-url") + 1]
            queue_name = queue_url.rsplit("/", 1)[-1]
            batch_size = int(args[args.index("--max-number-of-messages") + 1])
            queued = self.queue_messages.get(queue_name, [])
            batch, remainder = queued[:batch_size], queued[batch_size:]
            self.queue_messages[queue_name] = remainder
            return json.dumps({"Messages": batch})
        if args[:3] == ["aws", "s3api", "list-objects-v2"]:
            prefix = args[args.index("--prefix") + 1]
            limit = int(args[args.index("--max-keys") + 1])
            keys = sorted(key for key in self.s3_objects if key.startswith(prefix))[:limit]
            return json.dumps({"Contents": [{"Key": key} for key in keys]})
        if args[:3] == ["aws", "s3", "cp"]:
            source = args[3]
            if source == "-":
                return ""
            if not source.startswith("s3://"):
                raise AssertionError(f"unexpected s3 source: {source}")
            key = source.split("/", 3)[3]
            return json.dumps(self.s3_objects[key])
        raise AssertionError(f"unexpected aws invocation: {args}")


class TestWorkerCloudTransport(unittest.TestCase):
    def test_aws_cli_runner_wraps_subprocess_errors(self):
        runner = AwsCliRunner()
        with mock.patch("bridge.workers.cloud_transport.subprocess.run") as run_mock:
            run_mock.side_effect = subprocess.CalledProcessError(
                returncode=254,
                cmd=["aws", "sqs", "get-queue-url"],
                stderr="An error occurred (AWS.SimpleQueueService.NonExistentQueue) when calling the GetQueueUrl operation: The specified queue does not exist.\n",
            )
            with self.assertRaises(RuntimeError) as exc:
                runner.run(["aws", "sqs", "get-queue-url"])

        self.assertIn("AWS CLI failed", str(exc.exception))
        self.assertIn("NonExistentQueue", str(exc.exception))

    def test_build_store_export_plan_includes_objects_and_pending_signal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTaskStore(temp_dir)
            store.enqueue(
                WorkerTask(
                    task_id="task-plan-301",
                    thread_id="prep-weekly",
                    worker_id="planner",
                    task_type="plan",
                    payload={"items": ["count stock"]},
                    requires=("plan",),
                    effects=(),
                )
            )
            store.enqueue(
                WorkerTask(
                    task_id="task-arch-301",
                    thread_id="prep-weekly",
                    worker_id="archivist",
                    task_type="summarize",
                    payload={"texts": ["one", "two"]},
                    requires=("summarize",),
                    effects=(),
                )
            )
            run_next_task(store, build_default_runner(), "archivist")

            plan = build_store_export_plan(
                temp_dir,
                CloudTransportConfig(
                    bucket="cloudbridge-bucket",
                    region="us-east-2",
                    queue_prefix="cloudbridge",
                ),
            )

            self.assertEqual(len(plan.objects), 3)
            self.assertEqual(len(plan.messages), 1)
            self.assertEqual(len(plan.dead_letters), 0)
            self.assertEqual(plan.messages[0].queue_name, "cloudbridge-planner.fifo")
            self.assertEqual(
                plan.messages[0].body["s3_uri"],
                "s3://cloudbridge-bucket/tasks/planner/task-plan-301.json",
            )

    def test_apply_store_export_plan_uses_aws_cli_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTaskStore(temp_dir)
            store.enqueue(
                WorkerTask(
                    task_id="task-plan-302",
                    thread_id="prep-weekly",
                    worker_id="planner",
                    task_type="plan",
                    payload={"items": ["count stock"]},
                    requires=("plan",),
                    effects=(),
                )
            )
            plan = build_store_export_plan(
                temp_dir,
                CloudTransportConfig(
                    bucket="cloudbridge-bucket",
                    region="us-east-2",
                    queue_prefix="cloudbridge",
                ),
            )
            runner = FakeAwsCliRunner()

            out = apply_store_export_plan(
                plan,
                CloudTransportConfig(
                    bucket="cloudbridge-bucket",
                    region="us-east-2",
                    queue_prefix="cloudbridge",
                ),
                runner=runner,
            )

            self.assertEqual(out["object_count"], 1)
            self.assertEqual(out["message_count"], 1)
            self.assertEqual(runner.calls[0][0][:3], ["aws", "s3", "cp"])
            self.assertEqual(runner.calls[1][0][:3], ["aws", "sqs", "get-queue-url"])
            self.assertEqual(runner.calls[2][0][:3], ["aws", "sqs", "send-message"])

    def test_sync_store_from_cloud_payload_imports_task_and_receipt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = {
                "objects": [
                    {
                        "kind": "task",
                        "body": {
                            "task": {
                                "task_id": "task-plan-401",
                                "thread_id": "prep-weekly",
                                "worker_id": "planner",
                                "task_type": "plan",
                                "payload": {"items": ["count stock"]},
                                "requires": ["plan"],
                                "effects": [],
                            },
                            "status": "done",
                            "attempt": 2,
                            "max_attempts": 3,
                            "claimed_by": "planner",
                            "receipt_id": "rcpt:task-plan-401:2",
                            "last_error": None,
                            "result": {
                                "task_id": "task-plan-401",
                                "worker_id": "planner",
                                "role": "planner",
                                "status": "completed",
                                "output": {"steps": []},
                                "notes": [],
                            },
                        },
                    },
                    {
                        "kind": "receipt",
                        "body": {
                            "receipt_id": "rcpt:task-plan-401:2",
                            "task_id": "task-plan-401",
                            "worker_id": "planner",
                            "attempt": 2,
                            "status": "completed",
                        },
                    },
                ]
            }

            out = sync_store_from_cloud_payload(temp_dir, payload)
            store = FileTaskStore(temp_dir)

            self.assertEqual(out["task_ids"], ["task-plan-401"])
            self.assertEqual(out["receipt_ids"], ["rcpt:task-plan-401:2"])
            self.assertEqual(store.get("task-plan-401").status, "done")
            self.assertEqual(len(store.list_receipts()), 1)

    def test_failed_tasks_produce_dead_letters_and_can_be_replayed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTaskStore(temp_dir)
            task = WorkerTask(
                task_id="task-plan-402",
                thread_id="prep-weekly",
                worker_id="planner",
                task_type="plan",
                payload={"items": ["count stock"]},
                requires=("plan",),
                effects=(),
            )
            store.enqueue(task, max_attempts=1)
            receipt = store.claim("planner")
            self.assertIsNotNone(receipt)
            store.release(receipt.receipt_id, "boom")

            plan = build_store_export_plan(
                temp_dir,
                CloudTransportConfig(
                    bucket="cloudbridge-bucket",
                    region="us-east-2",
                    queue_prefix="cloudbridge",
                ),
            )
            self.assertEqual(len(plan.dead_letters), 1)
            self.assertEqual(plan.dead_letters[0].queue_name, "cloudbridge-planner-dlq.fifo")

            replay_out = replay_dead_letters(
                temp_dir,
                {"dead_letters": [message.to_dict() for message in plan.dead_letters]},
            )
            self.assertEqual(replay_out["task_ids"], ["task-plan-402"])
            self.assertEqual(store.get("task-plan-402").status, "pending")
            self.assertEqual(store.get("task-plan-402").attempt, 0)

    def test_fetch_cloud_payload_reads_s3_and_queue_sources(self):
        runner = FakeAwsCliRunner()
        runner.s3_objects = {
            "tasks/planner/task-plan-501.json": {
                "task": {
                    "task_id": "task-plan-501",
                    "thread_id": "prep-weekly",
                    "worker_id": "planner",
                    "task_type": "plan",
                    "payload": {"items": ["count stock"]},
                    "requires": ["plan"],
                    "effects": [],
                },
                "status": "pending",
                "attempt": 0,
                "max_attempts": 3,
                "claimed_by": None,
                "receipt_id": None,
                "last_error": None,
                "result": None,
            },
            "receipts/planner/rcpt__task-plan-501__1.json": {
                "receipt_id": "rcpt:task-plan-501:1",
                "task_id": "task-plan-501",
                "worker_id": "planner",
                "attempt": 1,
                "status": "open",
                "lease_expires_at": "2026-01-01T00:05:00Z",
            },
        }
        runner.queue_messages = {
            "cloudbridge-planner.fifo": [
                {
                    "Body": json.dumps(
                        {
                            "task_id": "task-plan-501",
                            "worker_id": "planner",
                            "s3_uri": "s3://cloudbridge-bucket/tasks/planner/task-plan-501.json",
                            "status": "pending",
                        }
                    ),
                    "ReceiptHandle": "receipt-1",
                    "Attributes": {
                        "MessageGroupId": "prep-weekly",
                        "MessageDeduplicationId": "task-plan-501",
                    },
                }
            ],
            "cloudbridge-planner-dlq.fifo": [
                {
                    "Body": json.dumps(
                        {
                            "task_id": "task-plan-502",
                            "worker_id": "planner",
                            "reason": "boom",
                            "task": {
                                "task": {
                                    "task_id": "task-plan-502",
                                    "thread_id": "prep-weekly",
                                    "worker_id": "planner",
                                    "task_type": "plan",
                                    "payload": {"items": ["order produce"]},
                                    "requires": ["plan"],
                                    "effects": [],
                                },
                                "status": "failed",
                                "attempt": 1,
                                "max_attempts": 3,
                                "claimed_by": None,
                                "receipt_id": None,
                                "last_error": "boom",
                                "result": None,
                            },
                        }
                    ),
                    "ReceiptHandle": "receipt-2",
                    "Attributes": {
                        "MessageGroupId": "prep-weekly",
                        "MessageDeduplicationId": "task-plan-502",
                    },
                }
            ],
        }

        payload = fetch_cloud_payload(
            CloudTransportConfig(
                bucket="cloudbridge-bucket",
                region="us-east-2",
                queue_prefix="cloudbridge",
            ),
            runner=runner,
            worker_ids=("planner",),
            task_object_limit=0,
            receipt_object_limit=1,
            queue_message_limit=1,
            include_dlq=True,
        )

        self.assertEqual(len(payload["objects"]), 2)
        self.assertEqual(len(payload["messages"]), 1)
        self.assertEqual(len(payload["dead_letters"]), 1)
        self.assertEqual(payload["messages"][0]["receipt_handle"], "receipt-1")
        self.assertEqual(payload["dead_letters"][0]["queue_name"], "cloudbridge-planner-dlq.fifo")

    def test_import_store_from_cloud_syncs_and_replays_live_payload(self):
        runner = FakeAwsCliRunner()
        runner.s3_objects = {
            "tasks/planner/task-plan-601.json": {
                "task": {
                    "task_id": "task-plan-601",
                    "thread_id": "prep-weekly",
                    "worker_id": "planner",
                    "task_type": "plan",
                    "payload": {"items": ["count stock"]},
                    "requires": ["plan"],
                    "effects": [],
                },
                "status": "pending",
                "attempt": 0,
                "max_attempts": 3,
                "claimed_by": None,
                "receipt_id": None,
                "last_error": None,
                "result": None,
            }
        }
        runner.queue_messages = {
            "cloudbridge-planner.fifo": [
                {
                    "Body": json.dumps(
                        {
                            "task_id": "task-plan-601",
                            "worker_id": "planner",
                            "s3_uri": "s3://cloudbridge-bucket/tasks/planner/task-plan-601.json",
                            "status": "pending",
                        }
                    ),
                    "ReceiptHandle": "receipt-3",
                    "Attributes": {
                        "MessageGroupId": "prep-weekly",
                        "MessageDeduplicationId": "task-plan-601",
                    },
                }
            ],
            "cloudbridge-planner-dlq.fifo": [
                {
                    "Body": json.dumps(
                        {
                            "task_id": "task-plan-602",
                            "worker_id": "planner",
                            "reason": "boom",
                            "task": {
                                "task": {
                                    "task_id": "task-plan-602",
                                    "thread_id": "prep-weekly",
                                    "worker_id": "planner",
                                    "task_type": "plan",
                                    "payload": {"items": ["order produce"]},
                                    "requires": ["plan"],
                                    "effects": [],
                                },
                                "status": "failed",
                                "attempt": 1,
                                "max_attempts": 3,
                                "claimed_by": None,
                                "receipt_id": None,
                                "last_error": "boom",
                                "result": None,
                            },
                        }
                    ),
                    "ReceiptHandle": "receipt-4",
                    "Attributes": {
                        "MessageGroupId": "prep-weekly",
                        "MessageDeduplicationId": "task-plan-602",
                    },
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            out = import_store_from_cloud(
                temp_dir,
                CloudTransportConfig(
                    bucket="cloudbridge-bucket",
                    region="us-east-2",
                    queue_prefix="cloudbridge",
                ),
                runner=runner,
                worker_ids=("planner",),
                task_object_limit=0,
                receipt_object_limit=0,
                queue_message_limit=1,
                include_dlq=True,
                replay_dlq=True,
                delete_fetched=True,
            )
            store = FileTaskStore(temp_dir)

            self.assertEqual(store.get("task-plan-601").status, "pending")
            self.assertEqual(store.get("task-plan-602").status, "pending")
            self.assertEqual(out["replayed"]["task_ids"], ["task-plan-602"])
            self.assertEqual(out["deleted"]["message_count"], 2)
            delete_calls = [call for call, _ in runner.calls if call[:3] == ["aws", "sqs", "delete-message"]]
            self.assertEqual(len(delete_calls), 2)


if __name__ == "__main__":
    unittest.main()
