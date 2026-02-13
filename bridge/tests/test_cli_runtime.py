import unittest

from bridge.cli import get_health, get_metrics, run_federate, run_route
from bridge.observability.metrics import reset


class TestCliRuntime(unittest.TestCase):
    def setUp(self) -> None:
        reset()

    def test_run_route_returns_destination(self):
        out = run_route(
            {
                "envelope": {
                    "gtid": "cb:1:bridge-1:thread-1",
                    "schema_version": "1.0",
                    "from_agent": "agent-a",
                    "to_agent": "agent-b",
                    "payload": {"task": "x"},
                },
                "registry": {"agent-b": "bridge-2"},
            }
        )
        self.assertEqual(out["destination"], "bridge-2")
        self.assertEqual(out["metrics"]["route"], 1)

    def test_run_route_rejects_non_object_registry(self):
        with self.assertRaises(ValueError):
            run_route(
                {
                    "envelope": {
                        "gtid": "cb:1:bridge-1:thread-1",
                        "schema_version": "1.0",
                        "from_agent": "agent-a",
                        "to_agent": "agent-b",
                        "payload": {"task": "x"},
                    },
                    "registry": [],
                }
            )

    def test_run_federate_self_trust_blocked(self):
        out = run_federate({"local_id": "bridge-1", "remote_id": "bridge-1", "known_bridges": []})
        self.assertFalse(out["trusted"])
        self.assertEqual(out["state"], "quarantined")
        self.assertEqual(out["metrics"]["federate"], 1)

    def test_health_and_metrics_shapes(self):
        self.assertEqual(get_health(), {"status": "ok"})
        self.assertEqual(get_metrics(), {"metrics": {}})


if __name__ == "__main__":
    unittest.main()
