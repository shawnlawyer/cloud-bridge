from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from bridge.steward_continuity import build_continuity_payload
from bridge.workflows.research_writing import bootstrap_research_writing


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
            self.assertIn("Write the alpha brief.", record["detail"])
            self.assertEqual(record["projectUrl"], "/projects/research-writing/research:alpha-brief/view")
            self.assertTrue(any(action["label"] == "Open" for action in record["actions"]))
            self.assertTrue(any(action["label"] == "Run thread" for action in record["actions"]))


if __name__ == "__main__":
    unittest.main()
