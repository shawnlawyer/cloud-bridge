from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "http://localhost:8080"


def _request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw)
    except URLError as exc:
        raise RuntimeError(f"unable to reach {BASE_URL}: {exc.reason}") from exc


def main() -> None:
    route_payload = {
        "envelope": {
            "gtid": "cb:1:local:test",
            "schema_version": "1.0",
            "from_agent": "a",
            "to_agent": "b",
            "payload": {},
        },
        "registry": {"b": "bridge-1"},
    }
    federate_payload = {
        "local_id": "bridge-1",
        "remote_id": "bridge-2",
        "known_bridges": [],
    }

    for method, path, payload in [
        ("GET", "/health", None),
        ("POST", "/route", route_payload),
        ("POST", "/federate", federate_payload),
        ("GET", "/metrics", None),
    ]:
        status, data = _request(method, path, payload)
        print(path, status, data)


if __name__ == "__main__":
    main()
