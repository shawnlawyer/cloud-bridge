from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.core.consensus import consensus
from bridge.core.envelope import Envelope
from bridge.core.routing import route
from bridge.federation.handshake import handshake
from bridge.federation.registry import AgentRecord, BridgeRecord, BridgeRegistry, Registry
from bridge.observability.metrics import record, reset, snapshot


def main() -> None:
    reset()

    # 1) Envelope creation
    envelope = Envelope(
        gtid="cb:1:bridge-1:thread-1",
        schema_version="1.0",
        from_agent="agent-a",
        to_agent="agent-b",
        payload={"task": "summarize"},
    )

    # 2) Routing
    agent_registry = Registry()
    agent_registry.register(AgentRecord(agent_id="agent-b", bridge_id="bridge-2"))
    destination = route(envelope, agent_registry)
    record("route")

    # 3) Federation handshake
    bridge_registry = BridgeRegistry()
    bridge_registry.register(BridgeRecord(bridge_id="bridge-1"))
    known_bridges = {record.bridge_id for record in bridge_registry.list_bridges()}
    handshake_ok = handshake("bridge-1", "bridge-2", known_bridges)
    record("handshake")

    # 4) Observability snapshot
    metrics = snapshot()

    # 5) Deterministic consensus (non-binding)
    selected = consensus({"agent-a": 0.9, "agent-b": 0.9, "agent-c": 0.7})

    print(
        {
            "envelope_id": str(envelope.id),
            "destination": destination,
            "handshake_ok": handshake_ok,
            "metrics": metrics,
            "consensus": selected,
        }
    )


if __name__ == "__main__":
    main()
