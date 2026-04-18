from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from bridge.steward_continuity import build_continuity_payload
from bridge.cli import run_research_writing_refresh, run_research_writing_run
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

    def test_review_receipt_moves_thread_into_reviewed_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir) / "store"
            workflow = bootstrap_research_writing(
                store_root,
                title="Reviewed Draft",
                objective="Produce a draft and mark it reviewed.",
            )

            run_research_writing_run(
                {
                    "store_root": str(store_root),
                    "thread_id": workflow["thread_id"],
                    "dispatch_limit": 8,
                    "pass_limit": 4,
                    "auto_assemble": True,
                }
            )

            first_payload = build_continuity_payload(str(store_root))
            artifact_id = first_payload["resumeTarget"]["latestArtifact"]["artifactId"]
            store = FileTaskStore(store_root)
            store.record_review_receipt(workflow["thread_id"], artifact_id=artifact_id)

            payload = build_continuity_payload(str(store_root))

            self.assertEqual(payload["resumeTarget"]["threadId"], workflow["thread_id"])
            self.assertEqual(payload["resumeTarget"]["state"], "reviewed")
            self.assertEqual(payload["resumeTarget"]["reviewStatus"], "reviewed")
            self.assertFalse(payload["resumeTarget"]["needsHumanReview"])
            self.assertEqual(payload["resumeTarget"]["resumeMode"], "continue")
            self.assertEqual(payload["resumeTarget"]["visualState"], "reviewed")
            self.assertIsNotNone(payload["resumeTarget"]["reviewReceipt"])
            self.assertTrue(any(action["label"] == "Continue thread" for action in payload["resumeTarget"]["actions"]))

    def test_reviewed_thread_can_be_refreshed_into_ready_to_continue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir) / "store"
            workflow = bootstrap_research_writing(
                store_root,
                title="Continue Reviewed Draft",
                objective="Review a draft, then queue the next pass.",
            )

            run_research_writing_run(
                {
                    "store_root": str(store_root),
                    "thread_id": workflow["thread_id"],
                    "dispatch_limit": 8,
                    "pass_limit": 4,
                    "auto_assemble": True,
                }
            )

            first_payload = build_continuity_payload(str(store_root))
            artifact_id = first_payload["resumeTarget"]["latestArtifact"]["artifactId"]
            store = FileTaskStore(store_root)
            store.record_review_receipt(workflow["thread_id"], artifact_id=artifact_id)

            run_research_writing_refresh(
                {
                    "store_root": str(store_root),
                    "thread_id": workflow["thread_id"],
                }
            )

            payload = build_continuity_payload(str(store_root))

            self.assertEqual(payload["resumeTarget"]["threadId"], workflow["thread_id"])
            self.assertEqual(payload["resumeTarget"]["state"], "ready")
            self.assertEqual(payload["resumeTarget"]["reviewStatus"], "reviewed")
            self.assertFalse(payload["resumeTarget"]["needsHumanReview"])
            self.assertEqual(payload["resumeTarget"]["resumeMode"], "continue")
            self.assertEqual(payload["resumeTarget"]["visualState"], "ready")
            self.assertIn("Run the next pass now that the last result is reviewed", payload["resumeTarget"]["nextAction"]["text"])

    def test_revision_note_shapes_reviewed_resume_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir) / "store"
            workflow = bootstrap_research_writing(
                store_root,
                title="Revision Requested",
                objective="Carry a revision note into continuity.",
            )

            run_research_writing_run(
                {
                    "store_root": str(store_root),
                    "thread_id": workflow["thread_id"],
                    "dispatch_limit": 8,
                    "pass_limit": 4,
                    "auto_assemble": True,
                }
            )

            first_payload = build_continuity_payload(str(store_root))
            artifact_id = first_payload["resumeTarget"]["latestArtifact"]["artifactId"]
            store = FileTaskStore(store_root)
            store.record_review_receipt(
                workflow["thread_id"],
                artifact_id=artifact_id,
                verdict="revise",
                note="Tighten the opening and keep the draft grounded.",
            )

            payload = build_continuity_payload(str(store_root))

            self.assertEqual(payload["resumeTarget"]["state"], "reviewed")
            self.assertEqual(payload["resumeTarget"]["reviewReceipt"]["verdict"], "revise")
            self.assertIn("revision note", payload["resumeTarget"]["nextAction"]["text"])
            self.assertIn("Tighten the opening", payload["resumeTarget"]["whyNow"])

    def test_blocked_thread_surfaces_exact_blocked_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir) / "store"
            workflow = bootstrap_research_writing(
                store_root,
                title="Blocked Planner",
                objective="Show why this thread is blocked.",
            )
            store = FileTaskStore(store_root)
            planner_task_id = f'{workflow["thread_id"]}:planner'
            planner_record = store.get(planner_task_id)
            blocked_planner = replace(
                planner_record,
                task=replace(
                    planner_record.task,
                    payload={
                        key: value for key, value in planner_record.task.payload.items() if key != "items"
                    },
                ),
            )
            store.upsert_task_record(blocked_planner, force=True)

            payload = build_continuity_payload(str(store_root))

            self.assertEqual(payload["resumeTarget"]["state"], "blocked")
            self.assertIn("missing payload keys: items", payload["resumeTarget"]["blockedReason"])
            self.assertIn("missing payload keys: items", payload["resumeTarget"]["whyNow"])
            self.assertIn("Planner plan is blocked", payload["resumeTarget"]["nextAction"]["text"])

    def test_failed_thread_surfaces_exact_failure_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir) / "store"
            workflow = bootstrap_research_writing(
                store_root,
                title="Failed Planner",
                objective="Show why this thread failed.",
            )
            store = FileTaskStore(store_root)
            planner_task_id = f'{workflow["thread_id"]}:planner'
            planner_record = store.get(planner_task_id)
            store.upsert_task_record(replace(planner_record, max_attempts=1), force=True)

            receipt = store.claim("planner", predicate=lambda record: record.task.thread_id == workflow["thread_id"])
            self.assertIsNotNone(receipt)
            store.release(receipt.receipt_id, "planner input broke")

            payload = build_continuity_payload(str(store_root))

            self.assertEqual(payload["resumeTarget"]["state"], "failed")
            self.assertIn("planner input broke", payload["resumeTarget"]["failedReason"])
            self.assertIn("planner input broke", payload["resumeTarget"]["whyNow"])
            self.assertIn("Planner plan failed", payload["resumeTarget"]["nextAction"]["text"])


if __name__ == "__main__":
    unittest.main()
