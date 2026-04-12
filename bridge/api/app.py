from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from bridge.cli import (
    get_health,
    get_metrics,
    run_federate,
    run_research_writing_assemble,
    run_research_writing_bootstrap,
    run_research_writing_import_folder,
    run_research_writing_list,
    run_research_writing_status,
    run_worker_artifact_list,
    run_worker_dispatch,
    run_worker_store_status,
    run_route,
    run_worker,
    run_worker_manifests,
)
from bridge.operator import render_operator_console, render_project_board, render_project_detail
from bridge.workers import FileTaskStore

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


@app.get("/projects/research-writing")
def research_writing_list_endpoint() -> dict:
    try:
        return run_research_writing_list({"store_root": _operator_store_root()})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/projects/research-writing/board", response_class=HTMLResponse)
def research_writing_board_endpoint() -> HTMLResponse:
    try:
        workflows = run_research_writing_list({"store_root": _operator_store_root()})["workflows"]
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HTMLResponse(render_project_board(workflows))


@app.post("/projects/research-writing/bootstrap")
def research_writing_bootstrap_endpoint(request: dict) -> dict:
    try:
        request = {"store_root": _operator_store_root(), **request}
        return run_research_writing_bootstrap(request)
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/projects/research-writing/import-folder")
def research_writing_import_folder_endpoint(request: dict) -> dict:
    try:
        request = {"store_root": _operator_store_root(), **request}
        return run_research_writing_import_folder(request)
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/projects/research-writing/{thread_id}")
def research_writing_status_endpoint(thread_id: str) -> dict:
    try:
        return run_research_writing_status({"store_root": _operator_store_root(), "thread_id": thread_id})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/projects/research-writing/{thread_id}/view", response_class=HTMLResponse)
def research_writing_detail_endpoint(thread_id: str) -> HTMLResponse:
    try:
        project = run_research_writing_status({"store_root": _operator_store_root(), "thread_id": thread_id})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HTMLResponse(render_project_detail(project))


@app.post("/projects/research-writing/{thread_id}/dispatch")
def research_writing_dispatch_endpoint(thread_id: str, limit: int = Query(default=4, ge=1, le=32)) -> dict:
    try:
        return run_worker_dispatch({"store_root": _operator_store_root(), "limit": limit, "thread_id": thread_id})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/projects/research-writing/{thread_id}/assemble")
def research_writing_assemble_endpoint(thread_id: str) -> dict:
    try:
        return run_research_writing_assemble({"store_root": _operator_store_root(), "thread_id": thread_id})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/artifacts")
def artifacts_endpoint(owner_id: str | None = None) -> dict:
    try:
        return run_worker_artifact_list({"store_root": _operator_store_root(), "owner_id": owner_id})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/artifacts/{artifact_id}")
def artifact_download_endpoint(artifact_id: str) -> FileResponse:
    store = FileTaskStore(_operator_store_root())
    try:
        artifact = store.get_artifact(artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    return FileResponse(path=artifact.path, media_type=artifact.media_type, filename=artifact.name)


@app.get("/metrics")
def metrics_endpoint() -> dict:
    return get_metrics()


@app.get("/health")
def health_endpoint() -> dict:
    return get_health()
