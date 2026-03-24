import tempfile
import unittest

from bridge.observability.metrics import reset
from bridge.cli import run_worker_dispatch, run_worker_enqueue


class TestWorkerDispatch(unittest.TestCase):
    def setUp(self) -> None:
        reset()

    def test_dispatch_uses_manifest_policies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_worker_enqueue(
                {
                    "store_root": temp_dir,
                    "task": {
                        "task_id": "task-plan-201",
                        "thread_id": "prep-weekly",
                        "worker_id": "planner",
                        "task_type": "plan",
                        "payload": {"items": ["count stock"]},
                        "requires": ["plan"],
                        "effects": [],
                    },
                }
            )
            run_worker_enqueue(
                {
                    "store_root": temp_dir,
                    "task": {
                        "task_id": "task-arch-201",
                        "thread_id": "prep-weekly",
                        "worker_id": "archivist",
                        "task_type": "summarize",
                        "payload": {"texts": ["one", "two"]},
                        "requires": ["summarize"],
                        "effects": [],
                    },
                }
            )
            run_worker_enqueue(
                {
                    "store_root": temp_dir,
                    "task": {
                        "task_id": "task-plan-202",
                        "thread_id": "prep-weekly",
                        "worker_id": "planner",
                        "task_type": "plan",
                        "payload": {"items": ["order produce"]},
                        "requires": ["plan"],
                        "effects": [],
                    },
                }
            )

            out = run_worker_dispatch({"store_root": temp_dir, "limit": 3})

            self.assertEqual(out["processed_count"], 3)
            self.assertEqual(
                [item["worker_id"] for item in out["results"]],
                ["planner", "planner", "archivist"],
            )
            self.assertEqual(out["metrics"]["worker_dispatch"], 1)
            self.assertEqual(out["metrics"]["worker_dispatch_step"], 3)

    def test_dispatch_skips_tasks_that_fail_manifest_admission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_worker_enqueue(
                {
                    "store_root": temp_dir,
                    "task": {
                        "task_id": "task-plan-203",
                        "thread_id": "prep-weekly",
                        "worker_id": "planner",
                        "task_type": "plan",
                        "payload": {"unexpected": ["count stock"]},
                        "requires": ["plan"],
                        "effects": [],
                    },
                }
            )
            run_worker_enqueue(
                {
                    "store_root": temp_dir,
                    "task": {
                        "task_id": "task-plan-204",
                        "thread_id": "prep-weekly",
                        "worker_id": "planner",
                        "task_type": "plan",
                        "payload": {"items": ["count stock"]},
                        "requires": ["plan"],
                        "effects": [],
                    },
                }
            )

            out = run_worker_dispatch({"store_root": temp_dir, "limit": 2})

            self.assertEqual(out["processed_count"], 1)
            self.assertEqual(out["results"][0]["task"]["task"]["task_id"], "task-plan-204")
            self.assertEqual(out["blocked"][0]["task_id"], "task-plan-203")
            self.assertEqual(out["blocked"][0]["reason"], "missing payload keys: items")


if __name__ == "__main__":
    unittest.main()
