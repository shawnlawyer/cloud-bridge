import unittest

from bridge.core.envelope import Envelope
from bridge.core.routing import MAX_HOPS, route
from bridge.federation.registry import AgentRecord, Registry


class TestRouting(unittest.TestCase):
    def test_route_to_known_agent(self):
        r = Registry()
        r.register(AgentRecord(agent_id="agent-b", bridge_id="bridge-2"))
        env = Envelope(
            gtid="cb:1:bridge-1:local",
            schema_version="1.0",
            from_agent="agent-a",
            to_agent="agent-b",
            payload={"msg": "hello"},
        )
        self.assertEqual(route(env, r), "bridge-2")

    def test_route_unknown_agent_raises(self):
        r = Registry()
        env = Envelope(
            gtid="cb:1:bridge-1:local",
            schema_version="1.0",
            from_agent="agent-a",
            to_agent="missing",
            payload={"msg": "hello"},
        )
        with self.assertRaises(KeyError):
            route(env, r)

    def test_route_hop_cap_raises(self):
        r = Registry()
        r.register(AgentRecord(agent_id="agent-b", bridge_id="bridge-2"))
        env = Envelope(
            gtid="cb:1:bridge-1:local",
            schema_version="1.0",
            from_agent="agent-a",
            to_agent="agent-b",
            payload={"msg": "hello"},
            hop_count=MAX_HOPS,
        )
        with self.assertRaises(RuntimeError):
            route(env, r)

    def test_route_below_hop_cap_ok(self):
        r = Registry()
        r.register(AgentRecord(agent_id="agent-b", bridge_id="bridge-2"))
        env = Envelope(
            gtid="cb:1:bridge-1:local",
            schema_version="1.0",
            from_agent="agent-a",
            to_agent="agent-b",
            payload={"msg": "hello"},
            hop_count=MAX_HOPS - 1,
        )
        self.assertEqual(route(env, r), "bridge-2")


if __name__ == "__main__":
    unittest.main()
