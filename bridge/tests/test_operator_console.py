import unittest

from bridge.operator import (
    render_drop_folder_page,
    render_inbox_page,
    render_operator_console,
    render_project_board,
    render_project_detail,
)


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

    def test_render_inbox_page_includes_actions_and_steward_label(self):
        inbox = render_inbox_page(
            {
                "summary": {
                    "ready_count": 1,
                    "blocked_count": 1,
                    "failed_count": 1,
                    "claimed_count": 1,
                    "expired_count": 1,
                    "thread_count": 1,
                },
                "threads": [
                    {
                        "thread_id": "research:alpha",
                        "title": "Alpha",
                        "project_url": "/projects/research-writing/research:alpha/view",
                        "ready_count": 1,
                        "blocked_count": 1,
                        "failed_count": 1,
                        "claimed_count": 1,
                        "task_counts": {"pending": 2, "failed": 1, "claimed": 1},
                    }
                ],
                "ready_tasks": [
                    {
                        "thread_title": "Alpha",
                        "project_url": "/projects/research-writing/research:alpha/view",
                        "worker_label": "Steward",
                        "task_type": "review",
                        "status": "pending",
                        "attempt": 0,
                        "max_attempts": 3,
                    }
                ],
                "blocked_tasks": [],
                "failed_tasks": [],
                "claimed_tasks": [],
            }
        )

        self.assertIn("Cloud Bridge Inbox", inbox)
        self.assertIn("Run Next 4", inbox)
        self.assertIn("Reclaim Expired", inbox)
        self.assertIn("Maintain Store", inbox)
        self.assertIn("Steward", inbox)

    def test_render_drop_folder_page_includes_register_and_scan_actions(self):
        html = render_drop_folder_page(
            {
                "summary": {"count": 1, "pending_count": 1, "missing_count": 0},
                "drop_folders": [
                    {
                        "name": "research-intake",
                        "folder_path": "/runtime/drop/research-intake",
                        "title": "Research Intake",
                        "thread_id": "research:drop:research-intake",
                        "project_url": "/projects/research-writing/research:drop:research-intake/view",
                        "exists": True,
                        "source_count": 2,
                        "pending_change_count": 1,
                        "changed_paths": ["notes.md"],
                        "removed_paths": [],
                        "last_import_at": "2026-04-12T10:00:00Z",
                        "last_scan_at": "2026-04-12T10:05:00Z",
                    }
                ],
            }
        )

        self.assertIn("Cloud Bridge Drop Folders", html)
        self.assertIn("Register Folder", html)
        self.assertIn("Scan All", html)
        self.assertIn("research-intake", html)


if __name__ == "__main__":
    unittest.main()
