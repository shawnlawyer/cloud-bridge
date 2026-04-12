import tempfile
import unittest
from pathlib import Path

from bridge.cli import (
    run_research_writing_assemble,
    run_research_writing_bootstrap,
    run_research_writing_status,
    run_worker_dispatch,
)
from bridge.workers import FileTaskStore


class TestResearchWritingWorkflow(unittest.TestCase):
    def test_bootstrap_dispatch_and_assemble_workflow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir, "source.md")
            source_path.write_text(
                "This is a source note about bounded local-first systems and private hubs.",
                encoding="utf-8",
            )

            boot = run_research_writing_bootstrap(
                {
                    "store_root": temp_dir,
                    "title": "Local Hub Primer",
                    "objective": "Explain the local private hub and outline research steps.",
                    "source_paths": [str(source_path)],
                    "constraints": ["local only", "zero cost"],
                }
            )

            self.assertEqual(boot["task_count"], 4)
            self.assertEqual(boot["artifact_count"], 2)

            dispatched = run_worker_dispatch({"store_root": temp_dir, "limit": 4})
            self.assertEqual(dispatched["processed_count"], 4)

            status = run_research_writing_status(
                {
                    "store_root": temp_dir,
                    "thread_id": boot["thread_id"],
                }
            )
            self.assertEqual(status["task_counts"]["done"], 4)
            self.assertEqual(status["artifact_count"], 2)
            self.assertEqual(status["title"], "Local Hub Primer")

            assembled = run_research_writing_assemble(
                {
                    "store_root": temp_dir,
                    "thread_id": boot["thread_id"],
                }
            )
            store = FileTaskStore(temp_dir)
            document = store.read_artifact_text(assembled["artifact"]["artifact_id"])

            self.assertIn("# Local Hub Primer", document)
            self.assertIn("## Research Digest", document)
            self.assertIn("## Working Plan", document)
            self.assertIn("## Draft", document)
            self.assertIn("scribe", assembled["included_workers"])


if __name__ == "__main__":
    unittest.main()
