import unittest

from bridge.observability.audit import emit
from bridge.observability.metrics import record, record_many, reset, snapshot


class TestObservability(unittest.TestCase):
    def setUp(self):
        reset()

    def test_metrics_accumulate(self):
        record("route")
        record("route")
        record("drop")
        self.assertEqual(snapshot(), {"route": 2, "drop": 1})

    def test_record_many(self):
        record_many(["a", "b", "a"])
        self.assertEqual(snapshot(), {"a": 2, "b": 1})

    def test_audit_emits_schema(self):
        out = emit({"event": "route", "details": {"id": "123"}})
        self.assertEqual(out["event"], "route")
        self.assertEqual(out["details"], {"id": "123"})
        self.assertIn("ts", out)


if __name__ == "__main__":
    unittest.main()
