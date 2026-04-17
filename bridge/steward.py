from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADAPTER = REPO_ROOT / "examples" / "steward-v1-workspace" / "scripts" / "steward-cloudbridge.mjs"


def _adapter_path() -> Path:
    raw = os.environ.get("CLOUD_BRIDGE_STEWARD_ADAPTER")
    return Path(raw).expanduser().resolve() if raw else DEFAULT_ADAPTER


def _base_args(operation: str) -> list[str]:
    args = ["node", str(_adapter_path()), operation, "--json"]
    db_path = os.environ.get("CLOUD_BRIDGE_STEWARD_DB_PATH")
    if db_path:
        args.extend(["--db", db_path])
    now_value = os.environ.get("CLOUD_BRIDGE_STEWARD_NOW")
    if now_value:
        args.extend(["--now", now_value])
    return args


def run_steward_adapter(operation: str, *extra: str) -> dict[str, Any]:
    process = subprocess.run(
        [*_base_args(operation), *extra],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip() or f"steward adapter failed ({process.returncode})"
        raise RuntimeError(detail)
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        detail = process.stdout.strip() or process.stderr.strip() or "invalid steward adapter output"
        raise RuntimeError(f"invalid steward adapter output: {detail}") from exc


def run_steward_home() -> dict[str, Any]:
    return run_steward_adapter("home")


def run_steward_ingest(text: str) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("text must be non-empty")
    return run_steward_adapter("ingest", "--text", text)


def run_steward_records(kind: str) -> dict[str, Any]:
    if not kind.strip():
        raise ValueError("kind must be non-empty")
    return run_steward_adapter("records", "--kind", kind)


def run_steward_approval(approval_ref: str, decision: str) -> dict[str, Any]:
    if not approval_ref.strip():
        raise ValueError("approval_ref must be non-empty")
    if decision not in {"approve", "deny"}:
        raise ValueError("decision must be approve or deny")
    return run_steward_adapter("approval", "--ref", approval_ref, "--decision", decision)


def run_steward_action(kind: str, record_ref: str, action: str) -> dict[str, Any]:
    if not kind.strip():
        raise ValueError("kind must be non-empty")
    if not record_ref.strip():
        raise ValueError("record_ref must be non-empty")
    if not action.strip():
        raise ValueError("action must be non-empty")
    return run_steward_adapter("action", "--kind", kind, "--ref", record_ref, "--action", action)
