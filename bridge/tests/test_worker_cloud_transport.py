import tempfile
import unittest

from bridge.workers import FileTaskStore, WorkerTask, build_default_runner, run_next_task
from bridge.workers.cloud_transport import (
    AwsCliRunner,
    CloudTransportConfig,
    apply_store_export_plan,
    build_store_export_plan,
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


if __name__ == "__main__":
    unittest.main()
