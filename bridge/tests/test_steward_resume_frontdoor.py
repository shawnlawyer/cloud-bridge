from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from bridge.operator import render_steward_frontdoor
from bridge.steward_continuity import build_continuity_payload
from bridge.workflows.research_writing import bootstrap_research_writing


class TestStewardResumeFrontDoor(unittest.TestCase):
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
        self.assertIn("Latest artifact", html)
        self.assertIn("Latest result", html)
        self.assertIn("Worker event", html)


if __name__ == "__main__":
    unittest.main()
