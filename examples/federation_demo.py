from bridge.federation.handshake import handshake
from bridge.federation.registry import AgentRecord, BridgeRecord, BridgeRegistry, Registry


r = Registry()
r.register(AgentRecord(agent_id="agent-a", bridge_id="bridge-1", capabilities=("analyze",)))
r.register(AgentRecord(agent_id="agent-b", bridge_id="bridge-2", capabilities=("summarize",)))

bridges = BridgeRegistry()
bridges.register(BridgeRecord(bridge_id="bridge-1"))
bridges.register(BridgeRecord(bridge_id="bridge-2"))

ok = handshake("bridge-1", "bridge-2", {b.bridge_id for b in bridges.list_bridges()})
print(r.lookup("agent-b"), ok)
