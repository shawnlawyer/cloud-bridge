import tempfile
import unittest

from bridge.workers import FileTaskStore, WorkerTask, build_default_runner, run_next_task
from bridge.workers.cloud_transport import (
    AwsCliRunner,
    CloudTransportConfig,
    apply_store_export_plan,
    build_store_export_plan,
    replay_dead_letters,
    sync_store_from_cloud_payload,
)


class FakeAwsCliRunner(AwsCliRunner):
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None]] = []

    def run(self, args: list[str], input_text: str | None = None) -> str:
        self.calls.append((args, input_text))
        if args[:3] == ["aws", "sqs", "get-queue-url"]:
            return "https://example.com/queue/cloudbridge-planner.fifo"
        return ""


class TestWorkerCloudTransport(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
