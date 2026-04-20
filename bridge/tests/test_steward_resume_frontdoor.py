from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from bridge.operator import render_steward_frontdoor, render_steward_lane
from bridge.operator.steward_priorities import prioritize_one_next_step
from bridge.steward_continuity import build_continuity_payload
from bridge.workflows.research_writing import bootstrap_research_writing


class TestStewardResumeFrontDoor(unittest.TestCase):
    def test_prioritize_one_next_step_keeps_approval_in_front(self):
        result = prioritize_one_next_step(
            {"kind": "approval", "text": "Decide now: Review budget hold."},
            {
                "threadId": "research:alpha",
                "title": "Alpha Project",
                "state": "ready",
                "reviewStatus": "reviewed",
                "needsHumanReview": False,
                "whyNow": "The latest result was reviewed and the next pass is already lined up.",
                "nextAction": {"text": "Run the next pass now that the last result is reviewed and the next work is lined up."},
                "actions": [{"label": "Run thread", "postUrl": "/projects/research-writing/research%3Aalpha/run?dispatch_limit=8&pass_limit=4"}],
            },
        )

        self.assertEqual(result["kind"], "approval")
        self.assertIn("Review budget hold", result["text"])

    def test_prioritize_one_next_step_promotes_review_needed_resume_target(self):
        result = prioritize_one_next_step(
            {"kind": "task", "text": "Fallback step."},
            {
                "threadId": "research:alpha",
                "title": "Alpha Project",
                "state": "review-needed",
                "reviewStatus": "pending",
                "needsHumanReview": True,
                "whyNow": "The latest pass needs a human look before the thread should move again.",
                "nextAction": {"text": "Review the latest output and decide what should move next."},
                "actions": [{"label": "Mark reviewed", "postUrl": "/projects/research-writing/research%3Aalpha/review?artifact_id=artifact%3A1"}],
            },
        )

        self.assertEqual(result["kind"], "continuity_review")
        self.assertEqual(result["threadId"], "research:alpha")
        self.assertIn("Review Alpha Project", result["text"])
        self.assertIn("human look", result["detail"])

    def test_prioritize_one_next_step_promotes_ready_continue_target(self):
        result = prioritize_one_next_step(
            {"kind": "task", "text": "Fallback step."},
            {
                "threadId": "research:alpha",
                "title": "Alpha Project",
                "state": "ready",
                "reviewStatus": "reviewed",
                "needsHumanReview": False,
                "whyNow": "The latest result was reviewed and the next pass is already lined up.",
                "nextAction": {"text": "Run the next pass now that the last result is reviewed and the next work is lined up."},
                "actions": [{"label": "Run thread", "postUrl": "/projects/research-writing/research%3Aalpha/run?dispatch_limit=8&pass_limit=4"}],
            },
        )

        self.assertEqual(result["kind"], "continuity_continue")
        self.assertIn("Run the next pass for Alpha Project", result["text"])
        self.assertIn("next pass is already lined up", result["detail"])

    def test_prioritize_one_next_step_promotes_revision_continue_target(self):
        result = prioritize_one_next_step(
            {"kind": "task", "text": "Fallback step."},
            {
                "threadId": "research:alpha",
                "title": "Alpha Project",
                "state": "ready",
                "reviewStatus": "reviewed",
                "reviewReceipt": {"verdict": "revise", "note": "Tighten the opening."},
                "needsHumanReview": False,
                "whyNow": "Local review asked for revisions and the next pass is already lined up.",
                "nextAction": {"text": "Run the next pass now that the revision note is saved and the next work is lined up."},
                "actions": [{"label": "Run thread", "postUrl": "/projects/research-writing/research%3Aalpha/run?dispatch_limit=8&pass_limit=4"}],
            },
        )

        self.assertEqual(result["kind"], "continuity_continue")
        self.assertIn("Run the revision pass for Alpha Project", result["text"])
        self.assertIn("revisions", result["detail"])

    def test_continuity_payload_exposes_resume_target_with_visuals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir) / "store"
            bootstrap_research_writing(
                store_root,
                title="Alpha Brief",
                objective="Write the alpha brief.",
            )

            payload = build_continuity_payload(str(store_root))

            self.assertIsNotNone(payload["resumeTarget"])
            self.assertEqual(payload["resumeTarget"]["title"], "Alpha Brief")
            self.assertIn("Run the next pass", payload["resumeTarget"]["nextAction"]["text"])
            self.assertEqual(payload["resumeTarget"]["resumeMode"], "dispatch")
            self.assertEqual(payload["resumeTarget"]["visualState"], "ready")
            self.assertTrue(payload["resumeTarget"]["visualAssetRefs"])
            self.assertEqual(payload["resumeTarget"]["visualAssetRefs"][0]["kind"], "hero")
            self.assertIn("/steward/assets/resume-ready-scene.svg", payload["resumeTarget"]["visualAssetRefs"][0]["src"])

    def test_frontdoor_renders_resume_work_visual_layer(self):
        html = render_steward_frontdoor(
            {
                "title": "One Next Step",
                "heartbeat": "HEARTBEAT_OK",
                "oneNextStep": {"kind": "task", "text": "Fallback step."},
                "resumeTarget": {
                    "title": "Alpha Project",
                    "nextAction": {
                        "text": "Review the latest output and decide what should move next.",
                        "label": "Open latest result",
                        "href": "/artifacts/artifact%3A1",
                    },
                    "whyNow": "The latest pass needs a human look before the thread should move again.",
                    "resumeMode": "review",
                    "state": "review-needed",
                    "reviewStatus": "pending",
                    "visualState": "review-needed",
                    "latestArtifact": {
                        "name": "alpha-draft.md",
                        "mediaType": "text/markdown",
                        "href": "/artifacts/artifact%3A1",
                    },
                    "latestResult": {
                        "workerId": "scribe",
                        "summary": "Draft assembled for review.",
                        "status": "completed",
                    },
                    "latestWorkerEvent": {
                        "event": "completed",
                        "detail": "task_id=research:alpha:scribe:draft worker_id=scribe",
                    },
                    "reviewReceipt": None,
                    "needsHumanReview": True,
                    "actions": [
                        {"label": "Open thread", "tone": "secondary", "href": "/projects/research-writing/research:alpha/view"},
                    ],
                    "visualAssetRefs": [
                        {
                            "kind": "hero",
                            "src": "/steward/assets/resume-review-needed-scene.svg",
                            "label": "Review needed scene",
                        }
                    ],
                },
                "todaySnapshot": {
                    "pendingApprovalCount": 1,
                    "overdueBillCount": 0,
                    "dueFollowupCount": 0,
                    "dueRoutineCount": 0,
                    "upcomingDateCount": 0,
                    "activeTaskCount": 1,
                    "activeRoomCount": 0,
                    "continuityCount": 1,
                },
                "currentContext": {},
                "lastWorked": {},
                "continuity": {"records": []},
            },
            {"summaries": []},
        )

        self.assertIn("Resume Work", html)
        self.assertIn("Alpha Project", html)
        self.assertIn("Review the latest output and decide what should move next.", html)
        self.assertIn("resume-review-needed-scene.svg", html)
        self.assertIn("Ready for review", html)
        self.assertIn("Still waiting for a local review.", html)
        self.assertIn("Latest artifact", html)
        self.assertIn("Latest result", html)
        self.assertIn("Worker event", html)

    def test_frontdoor_shows_review_note_when_saved(self):
        html = render_steward_frontdoor(
            {
                "title": "One Next Step",
                "heartbeat": "HEARTBEAT_OK",
                "oneNextStep": {"kind": "continuity_continue", "text": "Run the next pass for Alpha Project."},
                "resumeTarget": {
                    "threadId": "research:alpha",
                    "title": "Alpha Project",
                    "nextAction": {
                        "text": "Run the next pass now that the revision note is saved and the next work is lined up.",
                        "label": "Continue thread",
                        "postUrl": "/projects/research-writing/research%3Aalpha/refresh",
                    },
                    "whyNow": "Local review asked for revisions and the next pass is already lined up. Tighten the opening.",
                    "resumeMode": "continue",
                    "state": "ready",
                    "reviewStatus": "reviewed",
                    "reviewReceipt": {
                        "createdAt": "2026-04-18T09:20:00Z",
                        "verdict": "revise",
                        "note": "Tighten the opening.",
                    },
                    "needsHumanReview": False,
                    "actions": [{"label": "Continue thread", "postUrl": "/projects/research-writing/research%3Aalpha/refresh"}],
                    "visualState": "ready",
                    "visualAssetRefs": [],
                },
                "todaySnapshot": {},
                "currentContext": {},
                "lastWorked": {},
                "continuity": {"records": []},
            },
            {"summaries": []},
        )

        self.assertIn("Revision ready", html)
        self.assertIn("Changes requested", html)
        self.assertIn("Tighten the opening.", html)

    def test_frontdoor_renders_one_next_step_record_actions(self):
        html = render_steward_frontdoor(
            {
                "title": "One Next Step",
                "heartbeat": "Handle this first: Mortgage is overdue.",
                "oneNextStep": {
                    "kind": "bill",
                    "actionKind": "bills",
                    "ref": "bill:mortgage",
                    "text": "Handle this first: Mortgage is overdue.",
                    "detail": "overdue · due 2026-04-01 · $1626.37",
                    "actions": [
                        {"action": "mark_paid", "label": "Mark paid"},
                        {"label": "Open bills", "href": "/steward/view/bills", "tone": "secondary"},
                    ],
                },
                "todaySnapshot": {},
                "currentContext": {},
                "lastWorked": {},
                "continuity": {"records": []},
            },
            {"summaries": []},
        )

        self.assertIn("Mark paid", html)
        self.assertIn('data-kind="bills"', html)
        self.assertIn('data-record-action="mark_paid"', html)
        self.assertIn("Open bills", html)
        self.assertIn("[data-record-action]", html)

    def test_frontdoor_renders_lane_cards_with_status_copy(self):
        html = render_steward_frontdoor(
            {
                "title": "One Next Step",
                "heartbeat": "HEARTBEAT_OK",
                "oneNextStep": {"kind": "task", "text": "Continue with: clear counter."},
                "todaySnapshot": {
                    "pendingApprovalCount": 1,
                    "overdueBillCount": 1,
                    "dueFollowupCount": 2,
                    "dueRoutineCount": 1,
                    "upcomingDateCount": 1,
                    "activeTaskCount": 1,
                    "activeRoomCount": 1,
                    "continuityCount": 2,
                    "notificationCount": 3,
                },
                "currentContext": {
                    "activeTask": {"label": "Kitchen reset", "track": "home"},
                    "activeRoom": {"roomName": "Kitchen", "mode": "standard"},
                },
                "resumeTarget": {"title": "Alpha Project"},
                "lastWorked": {},
                "continuity": {"records": [{}, {}]},
            },
            {"summaries": [{"ref": "approval:demo", "title": "Review budget hold"}]},
        )

        self.assertIn("1 overdue now", html)
        self.assertIn("2 due now", html)
        self.assertIn("Active: Kitchen reset", html)
        self.assertIn("Active: Kitchen", html)
        self.assertIn("Next: Alpha Project", html)
        self.assertIn("3 waiting", html)
        self.assertIn("1 pending", html)

    def test_lane_view_collapses_json_and_shows_summary_chips(self):
        html = render_steward_lane(
            "Bills",
            {
                "kind": "bills",
                "summaries": [
                    {"title": "Mortgage", "detail": "overdue · due 2026-04-01", "ref": "bill:mortgage"}
                ],
                "records": [
                    {
                        "ref": "bill:mortgage",
                        "name": "Mortgage",
                        "state": "overdue",
                        "dueDate": "2026-04-01",
                        "amountText": "$1626.37",
                        "actions": [{"action": "mark_paid", "label": "Mark paid"}],
                    }
                ],
            },
        )

        self.assertIn("actionable", html)
        self.assertIn(">Overdue<", html)
        self.assertIn("Due 2026-04-01", html)
        self.assertIn("Amount $1626.37", html)
        self.assertIn("<details>", html)
        self.assertIn("Structured Records JSON", html)


if __name__ == "__main__":
    unittest.main()
