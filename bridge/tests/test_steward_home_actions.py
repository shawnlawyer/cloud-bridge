from __future__ import annotations

import unittest
from unittest.mock import patch

from bridge.api.app import _decorate_one_next_step


class TestStewardHomeActions(unittest.TestCase):
    @patch("bridge.api.app.run_steward_records")
    def test_decorate_one_next_step_enriches_bill_actions(self, run_steward_records_mock):
        run_steward_records_mock.return_value = {
            "kind": "bills",
            "records": [
                {
                    "ref": "bill:mortgage",
                    "name": "Mortgage",
                    "state": "overdue",
                    "detail": "overdue · due 2026-04-01 · $1626.37",
                    "actions": [
                        {"action": "mark_paid", "label": "Mark paid"},
                        {"action": "pause", "label": "Pause", "tone": "secondary"},
                    ],
                }
            ],
        }

        result = _decorate_one_next_step(
            {"kind": "bill", "text": "Handle this first: Mortgage is overdue."},
            {},
        )

        self.assertEqual(result["ref"], "bill:mortgage")
        self.assertEqual(result["actionKind"], "bills")
        self.assertEqual(result["actions"][0]["action"], "mark_paid")
        self.assertEqual(result["actions"][-1]["href"], "/steward/view/bills")
        self.assertIn("overdue", result["detail"])

    @patch("bridge.api.app.run_steward_records")
    def test_decorate_one_next_step_enriches_approval_actions(self, run_steward_records_mock):
        run_steward_records_mock.return_value = {
            "kind": "approvals",
            "records": [
                {
                    "ref": "approval:demo",
                    "title": "Review budget hold",
                    "detail": "Budget hold needs a decision.",
                    "status": "pending",
                }
            ],
        }

        result = _decorate_one_next_step(
            {
                "kind": "approval",
                "text": "Decide now: Review budget hold.",
                "approvalRef": "approval:demo",
            },
            {},
        )

        self.assertEqual(result["ref"], "approval:demo")
        self.assertEqual(result["actionKind"], "approvals")
        self.assertEqual(result["actions"][0]["decision"], "approve")
        self.assertEqual(result["actions"][1]["decision"], "deny")
        self.assertEqual(result["detail"], "Budget hold needs a decision.")

    def test_decorate_one_next_step_enriches_cash_with_bill_lane_link(self):
        result = _decorate_one_next_step(
            {"kind": "cash", "text": "Protect cash this week: cover essentials first."},
            {"cashPressure": {"text": "Weekly cash pressure: tight. Income $0.00, expenses $0.00, delta $0.00."}},
        )

        self.assertEqual(result["actionKind"], "bills")
        self.assertEqual(result["actions"][0]["href"], "/steward/view/bills")
        self.assertIn("Weekly cash pressure: tight", result["detail"])


if __name__ == "__main__":
    unittest.main()
