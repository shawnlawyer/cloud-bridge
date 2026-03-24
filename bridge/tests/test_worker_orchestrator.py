import tempfile
import unittest

from bridge.observability.metrics import reset
from bridge.cli import (
    run_ingest_chat_export,
    run_worker_enqueue,
    run_worker_manifests,
    run_worker_process,
    run_worker_store_list,
)


class TestWorkerOrchestrator(unittest.TestCase):
    def setUp(self) -> None:
        reset()

    def test_manifest_listing_returns_defaults(self):
        out = run_worker_manifests()
        self.assertEqual([item["worker_id"] for item in out["manifests"]], ["archivist", "scribe", "planner", "guardian"])
        self.assertIn("admission_rules", out["manifests"][0])
        self.assertEqual(out["metrics"]["worker_manifest_list"], 1)

    def test_enqueue_list_and_process_next_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            enqueue_out = run_worker_enqueue(
                {
                    "store_root": temp_dir,
                    "task": {
                        "task_id": "task-plan-100",
                        "thread_id": "prep-weekly",
                        "worker_id": "planner",
                        "task_type": "plan",
                        "payload": {"items": ["count stock", "order produce"]},
                        "requires": ["plan"],
                        "effects": [],
                    },
                    "max_attempts": 2,
                }
            )
            self.assertEqual(enqueue_out["task"]["status"], "pending")

            list_out = run_worker_store_list({"store_root": temp_dir})
            self.assertEqual(len(list_out["tasks"]), 1)

            process_out = run_worker_process({"store_root": temp_dir, "worker_id": "planner"})
            self.assertTrue(process_out["processed"])
            self.assertEqual(process_out["task"]["status"], "done")
            self.assertEqual(process_out["result"]["status"], "completed")
            self.assertEqual(process_out["metrics"]["worker_process"], 1)

    def test_ingest_command_enqueues_archivist_tasks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sample_path = f"{temp_dir}/sample.json"
            with open(sample_path, "w", encoding="utf-8") as handle:
                handle.write(
                    '[{"id":"conv-1","title":"One","messages":[{"role":"user","text":"hello"},{"role":"assistant","text":"hi"}]}]'
                )

            out = run_ingest_chat_export(
                {
                    "input_path": sample_path,
                    "store_root": temp_dir,
                    "max_attempts": 2,
                }
            )
            self.assertEqual(out["ingested"]["conversation_count"], 1)
            self.assertEqual(out["ingested"]["task_ids"], ["ingest:conv-1"])
            self.assertEqual(out["metrics"]["worker_ingest"], 1)
            self.assertEqual(out["metrics"]["worker_enqueue"], 1)


if __name__ == "__main__":
    unittest.main()
