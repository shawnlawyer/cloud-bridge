from __future__ import annotations

from fastapi import FastAPI, HTTPException

from bridge.cli import get_health, get_metrics, run_federate, run_route, run_worker

app = FastAPI(title="Cloud Bridge API", version="0.1.1")


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


@app.get("/metrics")
def metrics_endpoint() -> dict:
    return get_metrics()


@app.get("/health")
def health_endpoint() -> dict:
    return get_health()
