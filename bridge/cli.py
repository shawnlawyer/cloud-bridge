from __future__ import annotations

import argparse
import json
import sys

from bridge.core.envelope import Envelope
from bridge.core.routing import route
from bridge.federation.handshake import handshake
from bridge.federation.registry import AgentRecord, Registry
from bridge.observability.metrics import record, snapshot


def run_route(request: dict) -> dict:
    envelope_data = request.get("envelope")
    registry_data = request.get("registry")
    if not isinstance(envelope_data, dict):
        raise ValueError("envelope must be an object")
    if not isinstance(registry_data, dict):
        raise ValueError("registry must be an object")

    env = Envelope(**envelope_data)
    reg = Registry()
    for agent_id, bridge_id in registry_data.items():
        if not isinstance(agent_id, str) or not isinstance(bridge_id, str):
            raise ValueError("registry keys and values must be strings")
        reg.register(AgentRecord(agent_id=agent_id, bridge_id=bridge_id))

    destination = route(env, reg)
    record("route")
    return {"destination": destination, "metrics": snapshot()}


def run_federate(request: dict) -> dict:
    local_id = request.get("local_id")
    remote_id = request.get("remote_id")
    known = request.get("known_bridges", [])

    if not isinstance(local_id, str) or not isinstance(remote_id, str):
        raise ValueError("local_id and remote_id must be strings")
    if not isinstance(known, list) or not all(isinstance(v, str) for v in known):
        raise ValueError("known_bridges must be a list of strings")

    trusted = handshake(local_id, remote_id, set(known))
    record("federate")
    return {
        "trusted": trusted,
        "state": "trusted" if trusted else "quarantined",
        "metrics": snapshot(),
    }


def get_metrics() -> dict:
    return {"metrics": snapshot()}


def get_health() -> dict:
    return {"status": "ok"}


def _read_json_stdin() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("stdin must contain a JSON object")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return data


def _emit(data: dict) -> None:
    json.dump(data, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cloud-bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("route", help="Route an envelope using stdin JSON")
    sub.add_parser("federate", help="Run handshake using stdin JSON")
    sub.add_parser("metrics", help="Show in-process metrics")
    sub.add_parser("health", help="Show service health")

    args = parser.parse_args(argv)

    try:
        if args.command == "route":
            _emit(run_route(_read_json_stdin()))
        elif args.command == "federate":
            _emit(run_federate(_read_json_stdin()))
        elif args.command == "metrics":
            _emit(get_metrics())
        else:
            _emit(get_health())
        return 0
    except (ValueError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
