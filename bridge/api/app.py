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
    run_research_writing_refresh,
    run_research_writing_review,
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
    render_steward_frontdoor,
    render_steward_lane,
)
from bridge.operator.steward_priorities import prioritize_one_next_step
from bridge.operator.steward_visuals import resolve_steward_visual_path
from bridge.steward import (
    run_steward_action,
    run_steward_approval,
    run_steward_home,
    run_steward_ingest,
    run_steward_records,
    run_steward_tick,
)
from bridge.steward_continuity import build_continuity_payload
from bridge.workers import FileTaskStore

app = FastAPI(title="Cloud Bridge API", version="0.1.1")


def _operator_store_root() -> str:
    return os.environ.get("CLOUD_BRIDGE_STORE_ROOT", "/tmp/cloud-bridge-store")


def _worker_event_snapshot() -> dict | None:
    try:
        state = run_worker_store_status({"store_root": _operator_store_root(), "event_limit": 1})
    except (TypeError, ValueError, KeyError, RuntimeError):
        return None

    event = next(iter(state.get("recent_events", [])), None)
    if not event:
        return None

    parts = []
    for key in ("task_id", "worker_id", "receipt_id", "artifact_id", "owner_id", "reason", "status"):
        value = event.get(key)
        if value:
            parts.append(f"{key}={value}")

    return {
        "event": event.get("event", "unknown"),
        "detail": " ".join(parts) if parts else "Latest worker event.",
        "raw": event,
    }


def _decorate_last_worked(home: dict, continuity: dict, worker_event: dict | None) -> dict:
    last_worked = dict(home.get("lastWorked", {}))
    task = _task_last_worked(last_worked.get("task"))
    room = _room_last_worked(last_worked.get("room"))
    steward = _steward_last_worked(last_worked.get("notification"), home.get("oneNextStep") or {})
    resume = _resume_last_worked(continuity.get("resumeTarget"), worker_event)

    if task is not None:
        last_worked["task"] = task
    if room is not None:
        last_worked["room"] = room
    if steward is not None:
        last_worked["steward"] = steward
    if resume is not None:
        last_worked["resume"] = resume

    last_worked["workerEvent"] = worker_event
    return last_worked


def _task_last_worked(item: dict | None) -> dict | None:
    if not item:
        return None

    context = item.get("context")
    if not context and item.get("track"):
        context = f"Track: {item['track']}"
    if not context and item.get("nextStep"):
        context = f"Next: {item['nextStep']}"

    actions = list(item.get("actions") or [])
    if not actions:
        actions.append({"label": "Open tasks", "href": "/steward/view/tasks", "tone": "secondary"})

    return {
        **item,
        "label": item.get("label") or item.get("title") or "Recent task",
        "detail": item.get("detail") or item.get("status") or "Recent task work.",
        "context": context,
        "actions": actions,
    }


def _room_last_worked(item: dict | None) -> dict | None:
    if not item:
        return None

    context = item.get("context")
    if not context and item.get("mode"):
        context = f"Mode: {str(item['mode']).replace('_', ' ')}"
    if not context and item.get("pass"):
        context = f"Pass: {item['pass']}"

    actions = list(item.get("actions") or [])
    if not actions:
        actions.append({"label": "Open rooms", "href": "/steward/view/rooms", "tone": "secondary"})

    return {
        **item,
        "label": item.get("label") or item.get("roomName") or item.get("title") or "Recent room",
        "detail": item.get("detail") or item.get("status") or "Recent room work.",
        "context": context,
        "actions": actions,
    }


def _steward_last_worked(notification: dict | None, one_next_step: dict) -> dict | None:
    source = notification or one_next_step
    if not source:
        return None

    context = source.get("context")
    kind = source.get("kind") or one_next_step.get("kind")
    if not context and kind:
        context = f"Lane: {str(kind).replace('_', ' ')}"

    actions = list(source.get("actions") or [])
    if not actions:
        actions.append(
            {
                "label": "Open notifications",
                "href": "/steward/view/notification_events",
                "tone": "secondary",
            }
        )

    return {
        **source,
        "label": source.get("title") or source.get("text") or source.get("label") or "Current steward guidance",
        "detail": source.get("detail") or one_next_step.get("detail") or "Current next step.",
        "context": context,
        "actions": actions,
    }


def _resume_last_worked(resume_target: dict | None, worker_event: dict | None) -> dict | None:
    if not resume_target:
        if not worker_event:
            return None
        return {
            "label": str(worker_event.get("event") or "Worker").replace("_", " ").title(),
            "detail": worker_event.get("detail") or "Recent worker movement.",
            "context": "Most recent worker movement.",
            "status": "worker",
            "actions": [
                {
                    "label": "Open continuity",
                    "href": "/steward/view/continuity",
                    "tone": "secondary",
                }
            ],
        }

    actions = list(resume_target.get("actions") or [])
    if not actions and resume_target.get("projectUrl"):
        actions.append({"label": "Open thread", "href": resume_target["projectUrl"], "tone": "secondary"})
    if not actions:
        actions.append({"label": "Open continuity", "href": "/steward/view/continuity", "tone": "secondary"})

    latest_artifact = resume_target.get("latestArtifact") or {}
    latest_result = resume_target.get("latestResult") or {}
    latest_event = resume_target.get("latestWorkerEvent") or worker_event or {}
    context = None
    if latest_artifact.get("name"):
        context = f"Latest artifact: {latest_artifact['name']}"
    elif latest_result.get("summary"):
        context = f"Latest result: {latest_result['summary']}"
    elif latest_event.get("detail"):
        context = str(latest_event["detail"])
    elif resume_target.get("whyNow"):
        context = str(resume_target["whyNow"])

    return {
        "label": resume_target.get("title") or "Resume work",
        "detail": (resume_target.get("nextAction") or {}).get("text")
        or resume_target.get("whyNow")
        or "Open the thread and keep it moving.",
        "context": context,
        "status": resume_target.get("resumeMode") or resume_target.get("visualState"),
        "actions": actions[:2],
        "threadId": resume_target.get("threadId"),
    }


def _enrich_workflows_with_continuity(workflows: list[dict], continuity: dict) -> list[dict]:
    records = {
        str(item.get("threadId")): item
        for item in continuity.get("records", [])
        if isinstance(item, dict) and item.get("threadId")
    }
    enriched = []
    for workflow in workflows:
        record = records.get(str(workflow.get("thread_id")))
        if not record:
            enriched.append(workflow)
            continue
        next_action = record.get("nextAction") or {}
        board_actions = []
        if next_action.get("label") and (next_action.get("href") or next_action.get("postUrl")):
            board_actions.append(
                {
                    "label": next_action.get("label"),
                    "tone": "primary",
                    "href": next_action.get("href"),
                    "postUrl": next_action.get("postUrl"),
                }
            )
        for action in list(record.get("actions") or []):
            duplicate = any(
                existing.get("label") == action.get("label")
                and existing.get("href") == action.get("href")
                and existing.get("postUrl") == action.get("postUrl")
                for existing in board_actions
            )
            if duplicate:
                continue
            board_actions.append(action)
        enriched.append(
            {
                **workflow,
                "board_state": record.get("state"),
                "board_visual_state": record.get("visualState"),
                "review_receipt": record.get("reviewReceipt"),
                "review_status": record.get("reviewStatus"),
                "needs_human_review": record.get("needsHumanReview"),
                "board_detail": record.get("whyNow") or record.get("detail"),
                "board_next_action": next_action,
                "board_actions": board_actions[:2],
            }
        )
    return enriched


def _decorate_steward_home(home: dict) -> dict:
    continuity = build_continuity_payload(_operator_store_root())
    worker_event = _worker_event_snapshot()
    one_next_step = prioritize_one_next_step(home.get("oneNextStep") or {}, continuity.get("resumeTarget"))
    last_worked = _decorate_last_worked(home, continuity, worker_event)
    snapshot = dict(home.get("todaySnapshot", {}))
    snapshot["continuityCount"] = len(continuity.get("records", []))
    return {
        **home,
        "oneNextStep": one_next_step,
        "lastWorked": last_worked,
        "todaySnapshot": snapshot,
        "continuity": continuity,
        "resumeTarget": continuity.get("resumeTarget"),
    }


@app.get("/", response_class=HTMLResponse)
def steward_frontdoor_endpoint() -> HTMLResponse:
    try:
        home = _decorate_steward_home(run_steward_home())
        approvals = run_steward_records("approvals")
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HTMLResponse(render_steward_frontdoor(home, approvals))


@app.get("/steward/home")
def steward_home_endpoint() -> dict:
    try:
        return _decorate_steward_home(run_steward_home())
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/steward/ingest")
def steward_ingest_endpoint(request: dict) -> dict:
    text = request.get("text", "")
    try:
        return run_steward_ingest(str(text))
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/steward/records")
def steward_records_endpoint(kind: str = Query(...)) -> dict:
    try:
        if kind == "continuity":
            return build_continuity_payload(_operator_store_root())
        return run_steward_records(kind)
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/steward/view/{kind}", response_class=HTMLResponse)
def steward_lane_view_endpoint(kind: str) -> HTMLResponse:
    try:
        payload = build_continuity_payload(_operator_store_root()) if kind == "continuity" else run_steward_records(kind)
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    title = str(payload.get("kind", kind)).replace("_", " ").title()
    return HTMLResponse(render_steward_lane(title, payload))


@app.get("/steward/assets/{asset_name}")
def steward_asset_endpoint(asset_name: str) -> FileResponse:
    try:
        asset_path = resolve_steward_visual_path(asset_name)
    except KeyError:
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(path=asset_path)


@app.post("/steward/approval")
def steward_approval_endpoint(request: dict) -> dict:
    approval_ref = request.get("approval_ref", "")
    decision = request.get("decision", "")
    try:
        payload = run_steward_approval(str(approval_ref), str(decision))
        if isinstance(payload.get("frontDoor"), dict):
            payload["frontDoor"] = _decorate_steward_home(payload["frontDoor"])
        return payload
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/steward/action")
def steward_action_endpoint(request: dict) -> dict:
    kind = request.get("kind", "")
    record_ref = request.get("ref", "")
    action = request.get("action", "")
    try:
        payload = run_steward_action(str(kind), str(record_ref), str(action))
        if isinstance(payload.get("frontDoor"), dict):
            payload["frontDoor"] = _decorate_steward_home(payload["frontDoor"])
        return payload
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/steward/tick")
def steward_tick_endpoint(request: dict | None = None) -> dict:
    mode = (request or {}).get("mode", "all")
    try:
        payload = run_steward_tick(str(mode))
        if isinstance(payload.get("frontDoor"), dict):
            payload["frontDoor"] = _decorate_steward_home(payload["frontDoor"])
        return payload
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        workflows = run_research_writing_list({"store_root": _operator_store_root()})["workflows"]
        continuity = build_continuity_payload(_operator_store_root())
        return {"workflows": _enrich_workflows_with_continuity(workflows, continuity)}
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/projects/research-writing/board", response_class=HTMLResponse)
def research_writing_board_endpoint() -> HTMLResponse:
    try:
        workflows = run_research_writing_list({"store_root": _operator_store_root()})["workflows"]
        continuity = build_continuity_payload(_operator_store_root())
        workflows = _enrich_workflows_with_continuity(workflows, continuity)
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


@app.post("/projects/research-writing/{thread_id}/review")
def research_writing_review_endpoint(
    thread_id: str,
    artifact_id: str | None = Query(default=None),
    result_task_id: str | None = Query(default=None),
    verdict: str = Query(default="approved"),
    note: str | None = Query(default=None),
) -> dict:
    try:
        return run_research_writing_review(
            {
                "store_root": _operator_store_root(),
                "thread_id": thread_id,
                "artifact_id": artifact_id,
                "result_task_id": result_task_id,
                "verdict": verdict,
                "note": note,
            }
        )
    except (TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/projects/research-writing/{thread_id}/refresh")
def research_writing_refresh_endpoint(thread_id: str) -> dict:
    try:
        return run_research_writing_refresh({"store_root": _operator_store_root(), "thread_id": thread_id})
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
