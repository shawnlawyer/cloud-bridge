from datetime import datetime, timezone


def emit(event: dict) -> dict:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event.get("event", "unknown"),
        "details": event.get("details", {}),
    }
    return record
