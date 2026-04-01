import tempfile
import unittest
from unittest import mock

from bridge.observability.metrics import reset
from bridge.cli import (
    run_ingest_chat_export,
    run_worker_cloud_fetch,
    run_worker_enqueue,
    run_worker_manifests,
    run_worker_process,
    run_worker_store_maintain,
    run_worker_store_list,
    run_worker_store_status,
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

    def test_store_status_reports_blocked_tasks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_worker_enqueue(
                {
                    "store_root": temp_dir,
                    "task": {
                        "task_id": "task-plan-401",
                        "thread_id": "prep-weekly",
                        "worker_id": "planner",
                        "task_type": "plan",
                        "payload": {"unexpected": ["count stock"]},
                        "requires": ["plan"],
                        "effects": [],
                    },
                }
            )

            out = run_worker_store_status({"store_root": temp_dir})

            self.assertEqual(out["task_counts"]["pending"], 1)
            self.assertEqual(out["blocked"][0]["task_id"], "task-plan-401")
            self.assertEqual(out["metrics"]["worker_store_status"], 1)

    def test_store_maintain_prunes_terminal_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for task_id in ("task-plan-402", "task-plan-403"):
                run_worker_enqueue(
                    {
                        "store_root": temp_dir,
                        "task": {
                            "task_id": task_id,
                            "thread_id": "prep-weekly",
                            "worker_id": "planner",
                            "task_type": "plan",
                            "payload": {"items": ["count stock"]},
                            "requires": ["plan"],
                            "effects": [],
                        },
                    }
                )
                run_worker_process({"store_root": temp_dir, "worker_id": "planner"})

            out = run_worker_store_maintain(
                {"store_root": temp_dir, "keep_done": 1, "keep_failed": 0, "event_keep": 10}
            )

            self.assertEqual(len(out["pruned"]["deleted_task_ids"]), 1)
            self.assertEqual(out["summary"]["task_counts"]["done"], 1)
            self.assertEqual(out["metrics"]["worker_store_maintain"], 1)

    def test_cloud_fetch_requires_explicit_opt_in(self):
        with mock.patch.dict("os.environ", {"CLOUD_BRIDGE_ENABLE_CLOUD": ""}, clear=False):
            with self.assertRaises(RuntimeError):
                run_worker_cloud_fetch(
                    {
                        "bucket": "cloudbridge-bucket",
                        "region": "us-east-2",
                        "queue_prefix": "cloudbridge",
                        "worker_ids": ["planner"],
                    }
                )


if __name__ == "__main__":
    unittest.main()
