import unittest

from bridge.operator import render_operator_console


class TestOperatorConsole(unittest.TestCase):
    def test_render_operator_console_includes_summary_and_events(self):
        html = render_operator_console(
            {
                "task_count": 3,
                "task_counts": {"pending": 1, "done": 2},
                "receipt_count": 1,
                "receipt_counts": {"open": 1},
                "artifact_count": 2,
                "event_count": 4,
                "expired_receipt_ids": ["rcpt:task-plan-1:1"],
                "blocked": [
                    {
                        "task_id": "task-plan-1",
                        "worker_id": "planner",
                        "task_type": "plan",
                        "reason": "missing payload keys: items",
                    }
                ],
                "recent_events": [
                    {"event": "artifact_written", "artifact_id": "artifact:1", "owner_id": "workflow:alpha"}
                ],
            }
        )

        self.assertIn("Cloud Bridge Operator Console", html)
        self.assertIn("artifact_written", html)
        self.assertIn("workflow:alpha", html)
        self.assertIn("task-plan-1", html)
        self.assertIn("artifact_count", html)


if __name__ == "__main__":
    unittest.main()
