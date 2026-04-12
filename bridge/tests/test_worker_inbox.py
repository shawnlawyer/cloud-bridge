import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bridge.inbox import build_inbox_state
from bridge.workflows import bootstrap_research_writing
from bridge.workers import FileTaskStore, WorkerTask


class TestWorkerInbox(unittest.TestCase):
    def test_build_inbox_state_groups_attention_and_threads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir, "source.md")
            source.write_text("source text", encoding="utf-8")
            workflow = bootstrap_research_writing(
                temp_dir,
                title="Inbox Alpha",
                objective="Make the inbox useful.",
                source_paths=[str(source)],
                constraints=["local only"],
                max_attempts=1,
            )
            thread_id = workflow["thread_id"]
            store = FileTaskStore(temp_dir, lease_seconds=30)

            receipt = store.claim("guardian", now=datetime(2026, 1, 1, tzinfo=timezone.utc))
            self.assertIsNotNone(receipt)
            store.release(receipt.receipt_id, "review failed")

            planner_receipt = store.claim(
                "planner",
                now=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            self.assertIsNotNone(planner_receipt)
            claimed_record = store.get(planner_receipt.task_id)
            claimed_record_path = store._task_path(claimed_record.task.task_id)
            self.assertTrue(claimed_record_path.exists())

            bad_task = WorkerTask(
                task_id="task-plan-bad-001",
                thread_id=thread_id,
                worker_id="planner",
                task_type="plan",
                payload={"unexpected": ["x"]},
                requires=("plan",),
                effects=(),
            )
            store.enqueue(bad_task)

            state = build_inbox_state(temp_dir, task_limit=20)

            self.assertEqual(state["summary"]["ready_count"], 2)
            self.assertEqual(state["summary"]["blocked_count"], 1)
            self.assertEqual(state["summary"]["failed_count"], 1)
            self.assertEqual(state["summary"]["claimed_count"], 1)
            self.assertEqual(state["threads"][0]["thread_id"], thread_id)
            self.assertEqual(state["threads"][0]["title"], "Inbox Alpha")
            self.assertEqual(state["failed_tasks"][0]["worker_label"], "Steward")
            self.assertEqual(state["blocked_tasks"][0]["blocked_reason"], "missing payload keys: items")

    def test_claimed_task_marks_expired_when_lease_is_past_due(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTaskStore(temp_dir, lease_seconds=30)
            task = WorkerTask(
                task_id="task-plan-lease-001",
                thread_id="lease-thread",
                worker_id="planner",
                task_type="plan",
                payload={"items": ["count stock"]},
                requires=("plan",),
                effects=(),
            )
            store.enqueue(task)
            receipt = store.claim("planner", now=datetime.now(timezone.utc) - timedelta(seconds=90))
            self.assertIsNotNone(receipt)

            state = build_inbox_state(temp_dir)

            self.assertTrue(state["claimed_tasks"][0]["expired"])
            self.assertEqual(state["summary"]["expired_count"], 1)


if __name__ == "__main__":
    unittest.main()
