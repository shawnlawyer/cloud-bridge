import tempfile
import unittest

from bridge.workers.store import FileTaskStore, ReceiptRecord, TaskRecord
from bridge.workers.contracts import WorkerTask


class TestWorkerStoreSync(unittest.TestCase):
    def test_upsert_task_prefers_newer_attempt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTaskStore(temp_dir)
            task = WorkerTask(
                task_id="task-plan-501",
                thread_id="prep-weekly",
                worker_id="planner",
                task_type="plan",
                payload={"items": ["count stock"]},
                requires=("plan",),
                effects=(),
            )
            store.enqueue(task, max_attempts=3)

            incoming = TaskRecord(
                task=task,
                status="done",
                attempt=2,
                max_attempts=3,
                claimed_by="planner",
                receipt_id="rcpt:task-plan-501:2",
                last_error=None,
                result={
                    "task_id": "task-plan-501",
                    "worker_id": "planner",
                    "role": "planner",
                    "status": "completed",
                    "output": {"steps": []},
                    "notes": [],
                },
            )

            chosen = store.upsert_task_record(incoming)
            self.assertEqual(chosen.status, "done")
            self.assertEqual(store.get("task-plan-501").attempt, 2)

    def test_upsert_receipt_prefers_terminal_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTaskStore(temp_dir)
            open_receipt = ReceiptRecord(
                receipt_id="rcpt:task-plan-502:1",
                task_id="task-plan-502",
                worker_id="planner",
                attempt=1,
                status="open",
            )
            completed_receipt = ReceiptRecord(
                receipt_id="rcpt:task-plan-502:1",
                task_id="task-plan-502",
                worker_id="planner",
                attempt=1,
                status="completed",
            )

            store.upsert_receipt_record(open_receipt)
            chosen = store.upsert_receipt_record(completed_receipt)

            self.assertEqual(chosen.status, "completed")
            self.assertEqual(store.list_receipts()[0].status, "completed")


if __name__ == "__main__":
    unittest.main()
