from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from bridge.cli import (
    get_health,
    get_metrics,
    run_drop_folder_list,
    run_drop_folder_register,
    run_drop_folder_scan,
    run_federate,
    run_research_writing_assemble,
    run_research_writing_bootstrap,
    run_research_writing_import_folder,
    run_research_writing_list,
    run_research_writing_run,
    run_research_writing_status,
    run_worker_artifact_list,
    run_worker_dispatch,
    run_worker_inbox,
    run_worker_reclaim,
    run_worker_store_maintain,
    run_worker_store_status,
    run_route,
    run_worker,
    run_worker_manifests,
)
from bridge.operator import (
    render_drop_folder_page,
    render_inbox_page,
    render_operator_console,
    render_project_board,
    render_project_detail,
)
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


@app.get("/inbox/state")
def inbox_state_endpoint(task_limit: int = Query(default=40, ge=1, le=200)) -> dict:
    try:
        return run_worker_inbox({"store_root": _operator_store_root(), "task_limit": task_limit})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/inbox", response_class=HTMLResponse)
def inbox_view_endpoint(task_limit: int = Query(default=40, ge=1, le=200)) -> HTMLResponse:
    try:
        state = run_worker_inbox({"store_root": _operator_store_root(), "task_limit": task_limit})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HTMLResponse(render_inbox_page(state))


@app.post("/inbox/dispatch")
def inbox_dispatch_endpoint(limit: int = Query(default=4, ge=1, le=32), thread_id: str | None = None) -> dict:
    try:
        return run_worker_dispatch(
            {"store_root": _operator_store_root(), "limit": limit, "thread_id": thread_id}
        )
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/inbox/reclaim")
def inbox_reclaim_endpoint() -> dict:
    try:
        return run_worker_reclaim({"store_root": _operator_store_root()})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/inbox/maintain")
def inbox_maintain_endpoint() -> dict:
    try:
        return run_worker_store_maintain({"store_root": _operator_store_root()})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/drop-folders")
def drop_folder_list_endpoint() -> dict:
    try:
        return run_drop_folder_list({"store_root": _operator_store_root()})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/drop-folders/view", response_class=HTMLResponse)
def drop_folder_view_endpoint() -> HTMLResponse:
    try:
        state = run_drop_folder_list({"store_root": _operator_store_root()})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HTMLResponse(render_drop_folder_page(state))


@app.post("/drop-folders/register")
def drop_folder_register_endpoint(request: dict) -> dict:
    try:
        request = {"store_root": _operator_store_root(), **request}
        return run_drop_folder_register(request)
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/drop-folders/scan")
def drop_folder_scan_endpoint(name: str | None = None) -> dict:
    try:
        return run_drop_folder_scan({"store_root": _operator_store_root(), "name": name})
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.post("/projects/research-writing/{thread_id}/run")
def research_writing_run_endpoint(
    thread_id: str,
    dispatch_limit: int = Query(default=8, ge=1, le=64),
    pass_limit: int = Query(default=4, ge=1, le=16),
) -> dict:
    try:
        return run_research_writing_run(
            {
                "store_root": _operator_store_root(),
                "thread_id": thread_id,
                "dispatch_limit": dispatch_limit,
                "pass_limit": pass_limit,
                "auto_assemble": True,
            }
        )
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
