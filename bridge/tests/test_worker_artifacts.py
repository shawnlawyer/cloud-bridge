import tempfile
import unittest
from pathlib import Path

from bridge.cli import run_worker_artifact_add, run_worker_artifact_list
from bridge.workers import FileTaskStore, WorkerTask, build_default_runner, run_next_task


class TestWorkerArtifacts(unittest.TestCase):
    def test_add_inline_and_file_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            inline_out = run_worker_artifact_add(
                {
                    "store_root": temp_dir,
                    "owner_id": "workflow:notes",
                    "name": "notes.md",
                    "content": "# Notes\n\nHello.",
                    "media_type": "text/markdown",
                }
            )
            source_path = Path(temp_dir, "source.txt")
            source_path.write_text("source body", encoding="utf-8")
            file_out = run_worker_artifact_add(
                {
                    "store_root": temp_dir,
                    "owner_id": "workflow:notes",
                    "input_path": str(source_path),
                }
            )

            listed = run_worker_artifact_list({"store_root": temp_dir, "owner_id": "workflow:notes"})
            store = FileTaskStore(temp_dir)

            self.assertEqual(len(listed["artifacts"]), 2)
            self.assertEqual(store.summarize()["artifact_count"], 2)
            self.assertEqual(
                store.read_artifact_text(inline_out["artifact"]["artifact_id"]),
                "# Notes\n\nHello.",
            )
            self.assertEqual(file_out["artifact"]["name"], "source.txt")

    def test_prune_removes_task_owned_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileTaskStore(temp_dir)
            task = WorkerTask(
                task_id="task-plan-701",
                thread_id="prep-weekly",
                worker_id="planner",
                task_type="plan",
                payload={"items": ["count stock"]},
                requires=("plan",),
                effects=(),
            )
            store.enqueue(task)
            run_next_task(store, build_default_runner(), "planner")
            artifact = store.write_artifact(
                owner_id="task-plan-701",
                name="task-plan-701.md",
                content="done",
                media_type="text/markdown",
            )

            out = store.prune(keep_done=0, keep_failed=0, event_keep=20)

            self.assertIn("task-plan-701", out["deleted_task_ids"])
            self.assertIn(artifact.artifact_id, out["deleted_artifact_ids"])
            self.assertEqual(store.list_artifacts(owner_id="task-plan-701"), ())


if __name__ == "__main__":
    unittest.main()
