import unittest

from bridge.cli import run_worker
from bridge.observability.metrics import reset
from bridge.workers import LocalWorkerRunner, WorkerDefinition, WorkerTask


class TestWorkers(unittest.TestCase):
    def setUp(self) -> None:
        reset()

    def test_planner_worker_completes_task(self):
        out = run_worker(
            {
                "task": {
                    "task_id": "task-plan-001",
                    "thread_id": "weekly-kitchen",
                    "worker_id": "planner",
                    "task_type": "plan",
                    "payload": {"items": ["inventory herbs", "review prep list"]},
                    "requires": ["plan"],
                    "effects": [],
                }
            }
        )
        self.assertEqual(out["result"]["status"], "completed")
        self.assertEqual(
            out["result"]["output"]["steps"],
            [
                {"order": 1, "item": "inventory herbs"},
                {"order": 2, "item": "review prep list"},
            ],
        )
        self.assertEqual(out["metrics"]["worker_run"], 1)
        self.assertEqual(out["metrics"]["worker_complete"], 1)

    def test_runner_rejects_side_effects(self):
        out = run_worker(
            {
                "task": {
                    "task_id": "task-plan-002",
                    "thread_id": "weekly-kitchen",
                    "worker_id": "planner",
                    "task_type": "plan",
                    "payload": {"items": ["inventory herbs"]},
                    "requires": ["plan"],
                    "effects": ["write_to_world"],
                }
            }
        )
        self.assertEqual(out["result"]["status"], "rejected")
        self.assertEqual(out["result"]["notes"], ["side effects are not permitted"])
        self.assertEqual(out["metrics"]["worker_run"], 1)
        self.assertEqual(out["metrics"]["worker_reject"], 1)

    def test_guardian_flags_proposed_effects(self):
        out = run_worker(
            {
                "task": {
                    "task_id": "task-guard-001",
                    "thread_id": "weekly-kitchen",
                    "worker_id": "guardian",
                    "task_type": "review",
                    "payload": {
                        "objective": "Prepare update",
                        "constraints": ["no writes"],
                        "proposed_effects": ["send_email"],
                    },
                    "requires": ["review"],
                    "effects": [],
                }
            }
        )
        self.assertEqual(out["result"]["status"], "completed")
        self.assertFalse(out["result"]["output"]["approved"])
        self.assertEqual(out["result"]["output"]["proposed_effects"], ["send_email"])

    def test_unknown_worker_raises(self):
        with self.assertRaises(KeyError):
            run_worker(
                {
                    "task": {
                        "task_id": "task-unknown-001",
                        "thread_id": "weekly-kitchen",
                        "worker_id": "unknown",
                        "task_type": "plan",
                        "payload": {"items": ["x"]},
                        "requires": [],
                        "effects": [],
                    }
                }
            )

    def test_runner_rejects_missing_capability(self):
        runner = LocalWorkerRunner()
        runner.register(
            WorkerDefinition(
                worker_id="planner-lite",
                role="planner",
                capabilities=("plan",),
                allowed_task_types=("plan",),
            ),
            lambda task: {"steps": []},
        )
        result = runner.run(
            WorkerTask(
                task_id="task-plan-003",
                thread_id="weekly-kitchen",
                worker_id="planner-lite",
                task_type="plan",
                payload={"items": []},
                requires=("prioritize",),
                effects=(),
            )
        )
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.notes, ("missing worker capabilities: prioritize",))


if __name__ == "__main__":
    unittest.main()
