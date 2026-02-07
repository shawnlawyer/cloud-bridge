from bridge.core.envelope import Envelope
from bridge.core.throttling import allow, WINDOW_SECONDS, MAX_MESSAGES


def simulate(count: int, bridge_id: str = "bridge-1") -> dict:
    allowed = 0
    denied = 0
    for i in range(count):
        _ = Envelope(
            gtid=f"cb:1:{bridge_id}:{i}",
            schema_version="1.0",
            from_agent="agent-a",
            to_agent="agent-b",
            payload={"i": i},
        )
        if allow(bridge_id):
            allowed += 1
        else:
            denied += 1
    return {"allowed": allowed, "denied": denied}


def expect_throttle(count: int) -> bool:
    result = simulate(count)
    # If we send more than MAX_MESSAGES in a single window, we should see denials.
    if count > MAX_MESSAGES:
        return result["denied"] > 0
    return result["denied"] == 0


if __name__ == "__main__":
    result = simulate(MAX_MESSAGES + 10)
    print(
        {
            "window_seconds": WINDOW_SECONDS,
            "max_messages": MAX_MESSAGES,
            **result,
            "throttle_expected": expect_throttle(MAX_MESSAGES + 10),
        }
    )
