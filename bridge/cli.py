from __future__ import annotations

import argparse
import json
import sys

from bridge.core.envelope import Envelope
from bridge.core.routing import route
from bridge.federation.handshake import handshake
from bridge.federation.registry import AgentRecord, Registry
from bridge.ingest.chat_export import ingest_chat_export
from bridge.observability.metrics import record, snapshot
from bridge.observability.metrics import record_many
from bridge.workers import (
    WorkerTask,
    build_default_runner,
    enqueue_task,
    list_manifests,
    list_store_tasks,
    process_next_task,
)


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


def run_worker(request: dict) -> dict:
    task_data = request.get("task")
    if not isinstance(task_data, dict):
        raise ValueError("task must be an object")

    runner = build_default_runner()
    task = WorkerTask(**task_data)
    result = runner.run(task)

    events = ["worker_run", "worker_complete"]
    if result.status == "rejected":
        events[-1] = "worker_reject"
    record_many(events)
    return {"result": result.to_dict(), "metrics": snapshot()}


def run_worker_manifests() -> dict:
    record("worker_manifest_list")
    return {"manifests": list(list_manifests()), "metrics": snapshot()}


def run_worker_enqueue(request: dict) -> dict:
    store_root = request.get("store_root")
    task_data = request.get("task")
    max_attempts = request.get("max_attempts", 3)

    if not isinstance(store_root, str) or not store_root:
        raise ValueError("store_root must be a non-empty string")
    if not isinstance(task_data, dict):
        raise ValueError("task must be an object")
    if not isinstance(max_attempts, int) or max_attempts <= 0:
        raise ValueError("max_attempts must be a positive integer")

    task = WorkerTask(**task_data)
    record_data = enqueue_task(store_root, task, max_attempts=max_attempts)
    record("worker_enqueue")
    return {"task": record_data.to_dict(), "metrics": snapshot()}


def run_worker_store_list(request: dict) -> dict:
    store_root = request.get("store_root")
    if not isinstance(store_root, str) or not store_root:
        raise ValueError("store_root must be a non-empty string")

    tasks = [record_data.to_dict() for record_data in list_store_tasks(store_root)]
    record("worker_store_list")
    return {"tasks": tasks, "metrics": snapshot()}


def run_worker_process(request: dict) -> dict:
    store_root = request.get("store_root")
    worker_id = request.get("worker_id")

    if not isinstance(store_root, str) or not store_root:
        raise ValueError("store_root must be a non-empty string")
    if not isinstance(worker_id, str) or not worker_id:
        raise ValueError("worker_id must be a non-empty string")

    out = process_next_task(store_root, worker_id)
    if out["error"] is not None:
        events = ["worker_process", "worker_process_error"]
    else:
        events = ["worker_process", "worker_process_complete" if out["processed"] else "worker_process_idle"]
    record_many(events)
    out["metrics"] = snapshot()
    return out


def run_ingest_chat_export(request: dict) -> dict:
    input_path = request.get("input_path")
    store_root = request.get("store_root")
    max_attempts = request.get("max_attempts", 3)

    if not isinstance(input_path, str) or not input_path:
        raise ValueError("input_path must be a non-empty string")
    if not isinstance(store_root, str) or not store_root:
        raise ValueError("store_root must be a non-empty string")
    if not isinstance(max_attempts, int) or max_attempts <= 0:
        raise ValueError("max_attempts must be a positive integer")

    out = ingest_chat_export(input_path, store_root, max_attempts=max_attempts)
    events = ["worker_ingest"] + (["worker_enqueue"] * out["task_count"])
    record_many(events)
    return {"ingested": out, "metrics": snapshot()}


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
    sub.add_parser("worker-run", help="Run one bounded worker task using stdin JSON")
    sub.add_parser("worker-manifests", help="List built-in worker manifests")
    worker_enqueue_parser = sub.add_parser("worker-enqueue", help="Enqueue one worker task into a local store")
    worker_enqueue_parser.add_argument("--store-root", required=True)
    worker_enqueue_parser.add_argument("--max-attempts", type=int, default=3)
    worker_store_list_parser = sub.add_parser("worker-store-list", help="List tasks in a local worker store")
    worker_store_list_parser.add_argument("--store-root", required=True)
    worker_process_parser = sub.add_parser("worker-process", help="Process one queued task for a worker")
    worker_process_parser.add_argument("--store-root", required=True)
    worker_process_parser.add_argument("--worker", required=True)
    ingest_parser = sub.add_parser("ingest-chat-export", help="Ingest a local chat export into the worker store")
    ingest_parser.add_argument("--input", required=True)
    ingest_parser.add_argument("--store-root", required=True)
    ingest_parser.add_argument("--max-attempts", type=int, default=3)
    sub.add_parser("metrics", help="Show in-process metrics")
    sub.add_parser("health", help="Show service health")

    args = parser.parse_args(argv)

    try:
        if args.command == "route":
            _emit(run_route(_read_json_stdin()))
        elif args.command == "federate":
            _emit(run_federate(_read_json_stdin()))
        elif args.command == "worker-run":
            _emit(run_worker(_read_json_stdin()))
        elif args.command == "worker-manifests":
            _emit(run_worker_manifests())
        elif args.command == "worker-enqueue":
            stdin_data = _read_json_stdin()
            _emit(
                run_worker_enqueue(
                    {
                        "store_root": args.store_root,
                        "task": stdin_data.get("task", stdin_data),
                        "max_attempts": args.max_attempts,
                    }
                )
            )
        elif args.command == "worker-store-list":
            _emit(run_worker_store_list({"store_root": args.store_root}))
        elif args.command == "worker-process":
            _emit(run_worker_process({"store_root": args.store_root, "worker_id": args.worker}))
        elif args.command == "ingest-chat-export":
            _emit(
                run_ingest_chat_export(
                    {
                        "input_path": args.input,
                        "store_root": args.store_root,
                        "max_attempts": args.max_attempts,
                    }
                )
            )
        elif args.command == "metrics":
            _emit(get_metrics())
        else:
            _emit(get_health())
        return 0
    except (TypeError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
