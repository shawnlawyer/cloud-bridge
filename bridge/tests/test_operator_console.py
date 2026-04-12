import unittest

from bridge.operator import render_operator_console, render_project_board, render_project_detail


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

    def test_render_project_pages_include_actions(self):
        board = render_project_board(
            [
                {
                    "thread_id": "research:alpha",
                    "title": "Alpha",
                    "objective": "Describe the alpha project.",
                    "source_count": 2,
                    "artifact_count": 3,
                    "task_counts": {"done": 2, "pending": 2},
                }
            ]
        )
        detail = render_project_detail(
            {
                "thread_id": "research:alpha",
                "title": "Alpha",
                "objective": "Describe the alpha project.",
                "constraints": ["local only"],
                "sources": [{"name": "alpha.md", "excerpt": "source excerpt"}],
                "tasks": [
                    {
                        "task": {"worker_id": "guardian", "task_type": "review"},
                        "status": "done",
                        "result": {"output": {"approved": True}, "notes": []},
                    }
                ],
                "task_counts": {"done": 1},
                "artifacts": [
                    {
                        "artifact_id": "artifact:1",
                        "name": "alpha-draft.md",
                        "media_type": "text/markdown",
                        "size_bytes": 123,
                    }
                ],
            }
        )

        self.assertIn("Create Project", board)
        self.assertIn("Open project", board)
        self.assertIn("Run Dispatch", detail)
        self.assertIn("Steward approved=True", detail)


if __name__ == "__main__":
    unittest.main()
