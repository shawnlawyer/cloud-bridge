from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from bridge.cli import (
    get_health,
    get_metrics,
    run_federate,
    run_worker_store_status,
    run_route,
    run_worker,
    run_worker_manifests,
)
from bridge.operator import render_operator_console

app = FastAPI(title="Cloud Bridge API", version="0.1.1")


def _operator_store_root() -> str:
    return os.environ.get("CLOUD_BRIDGE_STORE_ROOT", "/tmp/cloud-bridge-store")


@app.post("/route")
def route_endpoint(request: dict) -> dict:
    try:
        return run_route(request)
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/federate")
def federate_endpoint(request: dict) -> dict:
    try:
        return run_federate(request)
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/worker/run")
def worker_run_endpoint(request: dict) -> dict:
    try:
        return run_worker(request)
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/worker/manifests")
def worker_manifests_endpoint() -> dict:
    return run_worker_manifests()


@app.get("/operator/state")
def operator_state_endpoint() -> dict:
    try:
        return run_worker_store_status({"store_root": _operator_store_root(), "event_limit": 20})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/operator/console", response_class=HTMLResponse)
def operator_console_endpoint() -> HTMLResponse:
    try:
        state = run_worker_store_status({"store_root": _operator_store_root(), "event_limit": 20})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HTMLResponse(render_operator_console(state))


@app.get("/metrics")
def metrics_endpoint() -> dict:
    return get_metrics()


@app.get("/health")
def health_endpoint() -> dict:
    return get_health()
