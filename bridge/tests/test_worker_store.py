import tempfile
import unittest
from pathlib import Path

from bridge.workers import build_default_runner
from bridge.workers.contracts import WorkerDefinition, WorkerTask
from bridge.workers.manifests import list_default_manifests
from bridge.workers.runner import LocalWorkerRunner
from bridge.workers.store import FileTaskStore, run_next_task


class TestWorkerStore(unittest.TestCase):
    def test_manifests_cover_default_roles(self):
        manifests = list_default_manifests()
        self.assertEqual(
            tuple(manifest.worker_id for manifest in manifests),
            ("archivist", "scribe", "planner", "guardian"),
        )

    def test_claim_complete_persists_done_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTaskStore(temp_dir)
            runner = build_default_runner()
            task = WorkerTask(
                task_id="task-plan-010",
                thread_id="prep-weekly",
                worker_id="planner",
                task_type="plan",
                payload={"items": ["count stock", "order produce"]},
                requires=("plan",),
                effects=(),
            )
            store.enqueue(task)

            result = run_next_task(store, runner, "planner")
            record = store.get("task-plan-010")

            self.assertIsNotNone(result)
            self.assertEqual(result.status, "completed")
            self.assertEqual(record.status, "done")
            self.assertEqual(record.result["status"], "completed")
            self.assertTrue(Path(temp_dir, "events.jsonl").exists())

    def test_release_requeues_then_fails_on_max_attempts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTaskStore(temp_dir)
            runner = LocalWorkerRunner()
            runner.register(
                WorkerDefinition(
                    worker_id="scribe-lite",
                    role="scribe",
                    capabilities=("draft",),
                    allowed_task_types=("draft",),
                ),
                lambda task: (_ for _ in ()).throw(ValueError("draft failed")),
            )
            task = WorkerTask(
                task_id="task-draft-001",
                thread_id="prep-weekly",
                worker_id="scribe-lite",
                task_type="draft",
                payload={"title": "Update", "points": ["a"]},
                requires=("draft",),
                effects=(),
            )
            store.enqueue(task, max_attempts=2)

            with self.assertRaises(ValueError):
                run_next_task(store, runner, "scribe-lite")
            first_record = store.get("task-draft-001")
            self.assertEqual(first_record.status, "pending")
            self.assertEqual(first_record.attempt, 1)
            self.assertEqual(first_record.last_error, "draft failed")

            with self.assertRaises(ValueError):
                run_next_task(store, runner, "scribe-lite")
            second_record = store.get("task-draft-001")
            self.assertEqual(second_record.status, "failed")
            self.assertEqual(second_record.attempt, 2)
            self.assertEqual(second_record.last_error, "draft failed")

    def test_rejected_worker_result_is_finalized_not_retried(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTaskStore(temp_dir)
            runner = build_default_runner()
            task = WorkerTask(
                task_id="task-plan-011",
                thread_id="prep-weekly",
                worker_id="planner",
                task_type="plan",
                payload={"items": ["count stock"]},
                requires=("plan",),
                effects=("write_to_world",),
            )
            store.enqueue(task)

            result = run_next_task(store, runner, "planner")
            record = store.get("task-plan-011")

            self.assertIsNotNone(result)
            self.assertEqual(result.status, "rejected")
            self.assertEqual(record.status, "done")
            self.assertEqual(record.result["status"], "rejected")
            self.assertEqual(store.claim("planner"), None)


if __name__ == "__main__":
    unittest.main()
