import time

WINDOW_SECONDS = 1.0
MAX_MESSAGES = 20

_counts: dict[str, list[float]] = {}


def allow(bridge_id: str) -> bool:
    now = time.time()
    bucket = _counts.setdefault(bridge_id, [])
    bucket[:] = [t for t in bucket if now - t < WINDOW_SECONDS]

    if len(bucket) >= MAX_MESSAGES:
        return False

    bucket.append(now)
    return True
