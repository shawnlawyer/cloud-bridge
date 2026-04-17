from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from bridge.steward_continuity import build_continuity_payload
from bridge.cli import run_research_writing_run
from bridge.workflows.research_writing import bootstrap_research_writing
from bridge.workers import FileTaskStore, build_default_runner


class TestStewardContinuity(unittest.TestCase):
    def test_build_continuity_payload_surfaces_thread_resume_actions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir) / "store"
            bootstrap_research_writing(
                store_root,
                title="Alpha Brief",
                objective="Write the alpha brief.",
            )

            payload = build_continuity_payload(str(store_root))

            self.assertEqual(payload["schemaVersion"], "steward-cloudbridge/v1")
            self.assertEqual(payload["operation"], "records")
            self.assertEqual(payload["kind"], "continuity")
            self.assertEqual(len(payload["records"]), 1)

            record = payload["records"][0]
            self.assertEqual(record["title"], "Alpha Brief")
            self.assertIn("ready", record["detail"])
            self.assertEqual(record["projectUrl"], "/projects/research-writing/research:alpha-brief/view")
            self.assertTrue(any(action["label"] == "Open thread" for action in record["actions"]))
            self.assertTrue(any(action["label"] == "Run thread" for action in record["actions"]))
            self.assertEqual(record["resumeMode"], "dispatch")
            self.assertEqual(record["visualState"], "ready")
            self.assertTrue(record["visualAssetRefs"])
            self.assertEqual(payload["resumeTarget"]["threadId"], record["threadId"])

    def test_review_needed_thread_beats_plain_ready_thread(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir) / "store"
            review_workflow = bootstrap_research_writing(
                store_root,
                title="Alpha Review",
                objective="Review the alpha thread.",
            )
            ready_workflow = bootstrap_research_writing(
                store_root,
                title="Beta Ready",
                objective="Run the beta thread.",
            )
            store = FileTaskStore(store_root)

            guardian_task_id = f'{review_workflow["thread_id"]}:guardian'
            guardian_record = store.get(guardian_task_id)
            review_guardian = replace(
                guardian_record,
                task=replace(
                    guardian_record.task,
                    payload={
                        **guardian_record.task.payload,
                        "proposed_effects": ["ship without review"],
                    },
                ),
            )
            store.upsert_task_record(review_guardian, force=True)

            receipt = store.claim("guardian", predicate=lambda record: record.task.thread_id == review_workflow["thread_id"])
            self.assertIsNotNone(receipt)
            runner = build_default_runner()
            store.complete(receipt.receipt_id, runner.run(store.get(receipt.task_id).task))

            payload = build_continuity_payload(str(store_root))

            self.assertEqual(payload["resumeTarget"]["threadId"], review_workflow["thread_id"])
            self.assertEqual(payload["resumeTarget"]["state"], "review-needed")
            self.assertTrue(payload["resumeTarget"]["needsHumanReview"])
            self.assertTrue(payload["resumeTarget"]["latestResult"]["needsReview"])

            review_record = next(item for item in payload["records"] if item["threadId"] == review_workflow["thread_id"])
            ready_record = next(item for item in payload["records"] if item["threadId"] == ready_workflow["thread_id"])
            self.assertGreater(review_record["resumeScore"], ready_record["resumeScore"])

    def test_completed_thread_with_real_artifact_beats_fresh_ready_thread(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir) / "store"
            review_workflow = bootstrap_research_writing(
                store_root,
                title="Artifact Review",
                objective="Run to a usable draft artifact.",
            )
            ready_workflow = bootstrap_research_writing(
                store_root,
                title="Gamma Ready",
                objective="Stay queued for later.",
            )

            run_research_writing_run(
                {
                    "store_root": str(store_root),
                    "thread_id": review_workflow["thread_id"],
                    "dispatch_limit": 8,
                    "pass_limit": 4,
                    "auto_assemble": True,
                }
            )

            payload = build_continuity_payload(str(store_root))

            self.assertEqual(payload["resumeTarget"]["threadId"], review_workflow["thread_id"])
            self.assertEqual(payload["resumeTarget"]["state"], "done")
            self.assertTrue(payload["resumeTarget"]["needsHumanReview"])
            self.assertEqual(payload["resumeTarget"]["resumeMode"], "review")
            self.assertEqual(payload["resumeTarget"]["visualState"], "review-needed")
            self.assertEqual(payload["resumeTarget"]["latestArtifact"]["mediaType"], "text/markdown")
            self.assertIn("Open the latest result", payload["resumeTarget"]["nextAction"]["text"])

            review_record = next(item for item in payload["records"] if item["threadId"] == review_workflow["thread_id"])
            ready_record = next(item for item in payload["records"] if item["threadId"] == ready_workflow["thread_id"])
            self.assertGreater(review_record["resumeScore"], ready_record["resumeScore"])


if __name__ == "__main__":
    unittest.main()
