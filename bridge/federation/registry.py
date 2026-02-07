from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    bridge_id: str
    capabilities: tuple[str, ...] = ()
    mode: str = "read-only"


@dataclass(frozen=True)
class BridgeRecord:
    bridge_id: str
    capabilities: tuple[str, ...] = ()
    mode: str = "read-only"


class Registry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentRecord] = {}

    def register(self, record: AgentRecord) -> None:
        if record.agent_id in self._agents:
            raise ValueError("Agent already registered")
        self._agents[record.agent_id] = record

    def lookup(self, agent_id: str) -> str:
        if agent_id not in self._agents:
            raise KeyError("Unknown agent")
        return self._agents[agent_id].bridge_id

    def get(self, agent_id: str) -> AgentRecord:
        if agent_id not in self._agents:
            raise KeyError("Unknown agent")
        return self._agents[agent_id]

    def list_agents(self) -> tuple[AgentRecord, ...]:
        return tuple(self._agents.values())


class BridgeRegistry:
    def __init__(self) -> None:
        self._bridges: dict[str, BridgeRecord] = {}

    def register(self, record: BridgeRecord) -> None:
        if record.bridge_id in self._bridges:
            raise ValueError("Bridge already registered")
        self._bridges[record.bridge_id] = record

    def get(self, bridge_id: str) -> BridgeRecord:
        if bridge_id not in self._bridges:
            raise KeyError("Unknown bridge")
        return self._bridges[bridge_id]

    def list_bridges(self) -> tuple[BridgeRecord, ...]:
        return tuple(self._bridges.values())
