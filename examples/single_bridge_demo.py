from bridge.core.envelope import Envelope


env = Envelope(
    gtid="cb:1:bridge-1:local",
    schema_version="1.0",
    from_agent="agent-a",
    to_agent="agent-b",
    payload={"msg": "hello"},
)

print(env)
