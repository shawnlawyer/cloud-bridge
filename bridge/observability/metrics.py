_metrics: dict[str, int] = {}


def record(event: str) -> None:
    _metrics[event] = _metrics.get(event, 0) + 1


def snapshot() -> dict[str, int]:
    return dict(_metrics)


def reset() -> None:
    _metrics.clear()


def record_many(events: list[str]) -> None:
    for event in events:
        record(event)
