import tempfile
import unittest
from pathlib import Path

from bridge.cli import run_drop_folder_list, run_drop_folder_register, run_drop_folder_scan
from bridge.inbox import build_inbox_state
from bridge.workflows import describe_research_writing


class TestDropFolders(unittest.TestCase):
    def test_register_scan_and_refresh_drop_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir, "drop")
            folder.mkdir()
            Path(folder, "notes.md").write_text("local-first research note", encoding="utf-8")
            Path(folder, "outline.txt").write_text("outline thoughts", encoding="utf-8")
            Path(folder, "image.png").write_bytes(b"png")

            registered = run_drop_folder_register(
                {
                    "store_root": temp_dir,
                    "name": "research-intake",
                    "folder_path": str(folder),
                    "title": "Research Intake",
                    "objective": "Turn local source notes into bounded research tasks.",
                    "constraints": ["local only", "zero cost"],
                }
            )
            self.assertEqual(registered["drop_folder"]["thread_id"], "research:drop:research-intake")

            listed = run_drop_folder_list({"store_root": temp_dir})
            self.assertEqual(listed["summary"]["count"], 1)
            self.assertEqual(listed["summary"]["pending_count"], 1)
            self.assertEqual(listed["drop_folders"][0]["pending_change_count"], 2)

            first_scan = run_drop_folder_scan({"store_root": temp_dir})
            self.assertEqual(first_scan["imported_count"], 1)
            self.assertEqual(first_scan["refreshed_count"], 0)
            self.assertEqual(first_scan["drop_folders"][0]["status"], "imported")

            inbox = build_inbox_state(temp_dir)
            self.assertEqual(inbox["summary"]["ready_count"], 4)

            second_scan = run_drop_folder_scan({"store_root": temp_dir})
            self.assertEqual(second_scan["unchanged_count"], 1)
            self.assertEqual(second_scan["drop_folders"][0]["status"], "unchanged")

            Path(folder, "notes.md").write_text("local-first research note revised", encoding="utf-8")
            Path(folder, "summary.md").write_text("new file", encoding="utf-8")

            refreshed = run_drop_folder_scan({"store_root": temp_dir, "name": "research-intake"})
            self.assertEqual(refreshed["refreshed_count"], 1)
            self.assertEqual(refreshed["drop_folders"][0]["status"], "refreshed")

            status = describe_research_writing(temp_dir, "research:drop:research-intake")
            self.assertEqual(len(status["sources"]), 3)
            self.assertEqual(status["task_count"], 8)


if __name__ == "__main__":
    unittest.main()
