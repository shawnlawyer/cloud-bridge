import unittest

from bridge.federation.handshake import handshake
from bridge.federation.registry import AgentRecord, BridgeRecord, BridgeRegistry, Registry


class TestFederation(unittest.TestCase):
    def test_handshake_rejects_self(self):
        self.assertFalse(handshake("bridge-1", "bridge-1"))

    def test_handshake_rejects_duplicate(self):
        self.assertFalse(handshake("bridge-1", "bridge-2", {"bridge-2"}))

    def test_handshake_accepts_new(self):
        self.assertTrue(handshake("bridge-1", "bridge-2", {"bridge-3"}))

    def test_bridge_registry_duplicate_rejected(self):
        br = BridgeRegistry()
        br.register(BridgeRecord(bridge_id="bridge-1"))
        with self.assertRaises(ValueError):
            br.register(BridgeRecord(bridge_id="bridge-1"))

    def test_registry_list_agents(self):
        r = Registry()
        r.register(AgentRecord(agent_id="agent-a", bridge_id="bridge-1"))
        self.assertEqual(len(r.list_agents()), 1)


if __name__ == "__main__":
    unittest.main()
