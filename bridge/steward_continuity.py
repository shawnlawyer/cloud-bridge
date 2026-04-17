from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import quote

from bridge.inbox import build_inbox_state
from bridge.operator.steward_visuals import asset_refs_for_state
from bridge.workflows.research_writing import describe_research_writing
from bridge.workers import FileTaskStore

_DEFAULT_EVENT_LIMIT = 400
_PRIMARY_ARTIFACT_NAME = "research-packet.json"


def build_continuity_payload(store_root: str, task_limit: int = 20, event_limit: int = _DEFAULT_EVENT_LIMIT) -> dict:
    state = build_inbox_state(store_root, task_limit=task_limit)
    store = FileTaskStore(store_root)
    task_records = {record.task.task_id: record.to_dict() for record in store.list_tasks()}
    receipt_records = {record.receipt_id: record.to_dict() for record in store.list_receipts()}
    review_receipt_records: dict[str, list[dict]] = {}
    for record in store.list_review_receipts():
        review_receipt_records.setdefault(record.thread_id, []).append(record.to_dict())
    recent_events = store.recent_events(limit=event_limit)
    workflow_cache: dict[str, dict | None] = {}

    records = [
        _thread_record(
            store_root,
            item,
            task_records=task_records,
            receipt_records=receipt_records,
            review_receipt_records=review_receipt_records,
            recent_events=recent_events,
            workflow_cache=workflow_cache,
        )
        for item in state.get("threads", [])
    ]
    records.sort(key=lambda item: (-item["resumeScore"], item["title"], item["threadId"]))

    summaries = [
        {
            "ref": item["ref"],
            "title": item["title"],
            "detail": item["detail"],
            "state": item["state"],
            "threadId": item["threadId"],
            "whyNow": item["whyNow"],
            "resumeMode": item["resumeMode"],
        }
        for item in records[:8]
    ]

    return {
        "schemaVersion": "steward-cloudbridge/v1",
        "operation": "records",
        "kind": "continuity",
        "summaries": summaries,
        "records": records,
        "resumeTarget": _resume_target(records[0]) if records else None,
    }


def _thread_record(
    store_root: str,
    item: dict,
    *,
    task_records: dict[str, dict],
    receipt_records: dict[str, dict],
    review_receipt_records: dict[str, list[dict]],
    recent_events: list[dict],
    workflow_cache: dict[str, dict | None],
) -> dict:
    thread_id = item["thread_id"]
    encoded_thread = quote(thread_id, safe="")
    workflow = _workflow_state(store_root, thread_id, workflow_cache)
    owner_id = (workflow or {}).get("owner_id")
    latest_event, event_recency = _latest_thread_event(
        thread_id,
        owner_id=owner_id,
        task_records=task_records,
        receipt_records=receipt_records,
        recent_events=recent_events,
    )
    latest_result = _latest_result(workflow, latest_event)
    latest_artifact = _latest_artifact(workflow)
    review_receipt = _latest_review_receipt(
        thread_id,
        latest_artifact=latest_artifact,
        latest_result=latest_result,
        review_receipt_records=review_receipt_records,
    )
    review_status = _review_status(review_receipt, latest_artifact=latest_artifact, latest_result=latest_result)
    state = _thread_state(item, latest_result, latest_artifact=latest_artifact, review_status=review_status)
    needs_human_review = _needs_human_review(
        item,
        state=state,
        latest_result=latest_result,
        latest_artifact=latest_artifact,
        review_status=review_status,
    )
    visual_state = _visual_state(
        state,
        needs_human_review,
        review_status=review_status,
        latest_result=latest_result,
        latest_artifact=latest_artifact,
    )
    actions = _thread_actions(
        item,
        encoded_thread=encoded_thread,
        project_url=item.get("project_url"),
        latest_artifact=latest_artifact,
        latest_result=latest_result,
        state=state,
        review_status=review_status,
    )
    next_action = _next_action(
        item,
        state=state,
        actions=actions,
        latest_artifact=latest_artifact,
        review_status=review_status,
    )
    why_now = _why_now(
        item,
        state=state,
        latest_result=latest_result,
        latest_artifact=latest_artifact,
        review_status=review_status,
    )
    detail = _detail_text(why_now, latest_artifact=latest_artifact, latest_result=latest_result)
    resume_score = _resume_score(
        item,
        latest_event=latest_event,
        latest_artifact=latest_artifact,
        latest_result=latest_result,
        state=state,
        needs_human_review=needs_human_review,
        event_recency=event_recency,
        review_status=review_status,
    )

    record = {
        "ref": f"continuity:{thread_id}",
        "threadId": thread_id,
        "title": item.get("title", thread_id),
        "detail": detail,
        "state": state,
        "projectUrl": item.get("project_url"),
        "resumeScore": resume_score,
        "nextAction": next_action,
        "whyNow": why_now,
        "resumeMode": _resume_mode(
            state,
            next_action,
            latest_result=latest_result,
            latest_artifact=latest_artifact,
            needs_human_review=needs_human_review,
            review_status=review_status,
        ),
        "latestWorkerEvent": latest_event,
        "latestArtifact": latest_artifact,
        "latestResult": latest_result,
        "reviewReceipt": review_receipt,
        "reviewStatus": review_status,
        "needsHumanReview": needs_human_review,
        "actions": actions,
        "visualState": visual_state,
        "visualAssetRefs": asset_refs_for_state(visual_state),
    }
    return record


def _workflow_state(store_root: str, thread_id: str, workflow_cache: dict[str, dict | None]) -> dict | None:
    if thread_id in workflow_cache:
        return workflow_cache[thread_id]
    try:
        workflow = describe_research_writing(store_root, thread_id)
    except (KeyError, ValueError, RuntimeError):
        workflow = None
    workflow_cache[thread_id] = workflow
    return workflow


def _thread_state(
    item: dict,
    latest_result: dict | None,
    *,
    latest_artifact: dict | None,
    review_status: str,
) -> str:
    if item.get("blocked_count"):
        return "blocked"
    if item.get("failed_count"):
        return "failed"
    if item.get("expired_count"):
        return "review-needed"
    if latest_result and latest_result.get("needsReview") and review_status != "reviewed":
        return "review-needed"
    if item.get("ready_count"):
        return "ready"
    if item.get("claimed_count"):
        return "running"
    if review_status == "reviewed" and (latest_artifact or latest_result):
        return "reviewed"
    if item.get("task_counts", {}).get("done"):
        return "done"
    return "quiet"


def _thread_actions(
    item: dict,
    *,
    encoded_thread: str,
    project_url: str | None,
    latest_artifact: dict | None,
    latest_result: dict | None,
    state: str,
    review_status: str,
) -> list[dict]:
    actions: list[dict] = []

    if review_status == "reviewed" and project_url and state == "reviewed":
        actions.append(
            {
                "label": "Continue thread",
                "tone": "primary",
                "postUrl": f"/projects/research-writing/{encoded_thread}/refresh",
            }
        )

    if latest_artifact and latest_artifact.get("href"):
        actions.append(
            {
                "label": "Open latest result",
                "tone": "primary" if state in {"done", "review-needed"} else "secondary",
                "href": latest_artifact["href"],
            }
        )

    if latest_artifact and review_status != "reviewed":
        query = [f"artifact_id={quote(latest_artifact['artifactId'], safe='')}"]
        if latest_result and latest_result.get("taskId"):
            query.append(f"result_task_id={quote(str(latest_result['taskId']), safe='')}")
        actions.append(
            {
                "label": "Mark reviewed",
                "tone": "secondary",
                "postUrl": f"/projects/research-writing/{encoded_thread}/review?{'&'.join(query)}",
            }
        )

    if project_url:
        actions.append(
            {
                "label": "Open thread",
                "tone": "primary" if state in {"blocked", "failed", "quiet"} and not latest_artifact else "secondary",
                "href": project_url,
            }
        )

    if item.get("expired_count"):
        actions.append(
            {
                "label": "Reclaim stuck work",
                "tone": "primary",
                "postUrl": "/inbox/reclaim",
            }
        )

    if project_url and any(item.get(key) for key in ("ready_count", "blocked_count", "failed_count", "claimed_count")):
        actions.append(
            {
                "label": "Run thread",
                "tone": "primary" if state in {"ready", "running"} else "secondary",
                "postUrl": f"/projects/research-writing/{encoded_thread}/run?dispatch_limit=8&pass_limit=4",
            }
        )

    if item.get("ready_count"):
        actions.append(
            {
                "label": "Dispatch ready work",
                "tone": "secondary",
                "postUrl": f"/inbox/dispatch?limit=4&thread_id={encoded_thread}",
            }
        )

    return _dedupe_actions(actions)


def _dedupe_actions(actions: Iterable[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict] = []
    for item in actions:
        key = (
            str(item.get("label", "")),
            str(item.get("href", "")),
            str(item.get("postUrl", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _next_action(
    item: dict,
    *,
    state: str,
    actions: list[dict],
    latest_artifact: dict | None,
    review_status: str,
) -> dict:
    primary_action = next((action for action in actions if action.get("tone") == "primary"), actions[0] if actions else {})

    if state == "blocked":
        text = "Open the thread and clear the blocked path before anything else."
    elif state == "failed":
        text = "Review the failed worker pass and decide whether to retry or reshape it."
    elif state == "review-needed":
        if item.get("expired_count"):
            text = "Reclaim the stuck claim, then run the thread again."
        else:
            text = "Review the latest output and decide what should move next."
    elif state == "reviewed":
        text = "Queue the next pass when you want this thread moving again."
    elif state == "ready":
        if review_status == "reviewed":
            text = "Run the next pass now that the last result is reviewed and the next work is lined up."
        else:
            text = "Run the next pass while the ready work is already lined up."
    elif state == "running":
        text = "Check the running pass before queuing more work behind it."
    elif latest_artifact:
        if review_status == "reviewed":
            text = "The latest result is already reviewed. Open it again if you need the context."
        else:
            text = "Open the latest result, then mark it reviewed when you're done."
    else:
        text = "Open the thread and choose the next concrete move."

    return {
        "text": text,
        "label": primary_action.get("label"),
        "href": primary_action.get("href"),
        "postUrl": primary_action.get("postUrl"),
    }


def _why_now(
    item: dict,
    *,
    state: str,
    latest_result: dict | None,
    latest_artifact: dict | None,
    review_status: str,
) -> str:
    if state == "blocked":
        return f"{item.get('blocked_count', 0)} blocked task{'s' if item.get('blocked_count', 0) != 1 else ''} are waiting on a decision."
    if state == "failed":
        return f"{item.get('failed_count', 0)} failed task{'s' if item.get('failed_count', 0) != 1 else ''} need a clean recovery path."
    if state == "review-needed":
        if item.get("expired_count"):
            return f"{item.get('expired_count', 0)} claimed task{'s' if item.get('expired_count', 0) != 1 else ''} may be stuck."
        if latest_result and latest_result.get("needsReview"):
            return latest_result["summary"]
        return "The latest pass needs a human look before the thread should move again."
    if state == "reviewed":
        return "The latest result was reviewed locally and is waiting for the next pass."
    if state == "ready":
        if review_status == "reviewed":
            return "The latest result was reviewed and the next pass is already lined up."
        return f"{item.get('ready_count', 0)} ready task{'s' if item.get('ready_count', 0) != 1 else ''} can move right now on the local hub."
    if state == "running":
        return f"{item.get('claimed_count', 0)} worker claim{'s' if item.get('claimed_count', 0) != 1 else ''} are in motion already."
    if latest_artifact:
        if review_status != "reviewed":
            return f"{latest_artifact['name']} is waiting for a local review receipt."
        return f"{latest_artifact['name']} is the latest saved result for this thread."
    done_count = item.get("task_counts", {}).get("done", 0)
    if done_count:
        return f"{done_count} completed task{'s' if done_count != 1 else ''} are preserved here for continuity."
    return "This thread is quiet, but it is still the clearest place to resume work."


def _detail_text(why_now: str, *, latest_artifact: dict | None, latest_result: dict | None) -> str:
    parts = [why_now]
    if latest_artifact:
        parts.append(f"Latest artifact: {latest_artifact['name']}")
    if latest_result:
        parts.append(f"Latest result: {latest_result['summary']}")
    return " — ".join(parts[:3])


def _resume_mode(
    state: str,
    next_action: dict,
    *,
    latest_result: dict | None,
    latest_artifact: dict | None,
    needs_human_review: bool,
    review_status: str,
) -> str:
    if state in {"blocked", "failed", "review-needed"} or needs_human_review:
        return "review"
    if state == "reviewed":
        return "continue"
    if state == "ready":
        if review_status == "reviewed":
            return "continue"
        return "dispatch"
    if state == "running":
        return "monitor"
    if state == "done" and (latest_result or latest_artifact):
        return "review"
    if next_action.get("href"):
        return "open"
    return "dispatch"


def _latest_thread_event(
    thread_id: str,
    *,
    owner_id: str | None,
    task_records: dict[str, dict],
    receipt_records: dict[str, dict],
    recent_events: list[dict],
) -> tuple[dict | None, int]:
    for event_recency, event in enumerate(reversed(recent_events)):
        task_id = event.get("task_id")
        receipt_id = event.get("receipt_id")
        matched_thread = None

        if isinstance(task_id, str):
            task_record = task_records.get(task_id)
            if task_record:
                matched_thread = task_record["task"]["thread_id"]
        elif isinstance(receipt_id, str):
            receipt = receipt_records.get(receipt_id)
            if receipt:
                task_record = task_records.get(receipt["task_id"])
                if task_record:
                    matched_thread = task_record["task"]["thread_id"]

        if matched_thread != thread_id and event.get("owner_id") != owner_id:
            continue

        return _event_summary(event, task_records=task_records, receipt_records=receipt_records), event_recency

    return None, _DEFAULT_EVENT_LIMIT


def _event_summary(event: dict, *, task_records: dict[str, dict], receipt_records: dict[str, dict]) -> dict:
    task_id = event.get("task_id")
    receipt_id = event.get("receipt_id")
    worker_id = event.get("worker_id")
    if not worker_id and isinstance(receipt_id, str):
        worker_id = (receipt_records.get(receipt_id) or {}).get("worker_id")
    detail_parts = []
    for key in ("task_id", "worker_id", "artifact_id", "receipt_id", "owner_id", "reason", "status", "result_status"):
        value = event.get(key)
        if value:
            detail_parts.append(f"{key}={value}")
    return {
        "event": event.get("event", "unknown"),
        "detail": " ".join(detail_parts) if detail_parts else "Latest worker event.",
        "taskId": task_id,
        "workerId": worker_id,
        "artifactId": event.get("artifact_id"),
        "receiptId": receipt_id,
        "ownerId": event.get("owner_id"),
    }


def _latest_artifact(workflow: dict | None) -> dict | None:
    if not workflow:
        return None

    artifacts = workflow.get("artifacts", [])
    if not artifacts:
        return None

    if all(str(artifact.get("name", "")) == _PRIMARY_ARTIFACT_NAME for artifact in artifacts):
        return None

    ranked = sorted(artifacts, key=_artifact_sort_key, reverse=True)
    artifact = ranked[0]
    return {
        "artifactId": artifact["artifact_id"],
        "name": artifact["name"],
        "mediaType": artifact["media_type"],
        "createdAt": artifact["created_at"],
        "href": f"/artifacts/{quote(artifact['artifact_id'], safe='')}",
    }


def _artifact_sort_key(artifact: dict) -> tuple[int, str]:
    name = str(artifact.get("name", "")).lower()
    media_type = str(artifact.get("media_type", "")).lower()
    if name.endswith(".md") or media_type == "text/markdown":
        priority = 4
    elif media_type.startswith("text/") and name != _PRIMARY_ARTIFACT_NAME:
        priority = 3
    elif name != _PRIMARY_ARTIFACT_NAME:
        priority = 2
    else:
        priority = 1
    return (priority, str(artifact.get("created_at", "")))


def _latest_result(workflow: dict | None, latest_event: dict | None) -> dict | None:
    if not workflow:
        return None

    tasks = workflow.get("tasks", [])
    if not tasks:
        return None

    event_task_id = (latest_event or {}).get("taskId")
    if event_task_id:
        matched = next((item for item in tasks if item["task"]["task_id"] == event_task_id), None)
        summary = _result_summary(matched)
        if summary:
            return summary

    for item in sorted(tasks, key=_task_result_sort_key, reverse=True):
        summary = _result_summary(item)
        if summary:
            return summary
    return None


def _task_result_sort_key(task_record: dict) -> tuple[int, str, str]:
    status = str(task_record.get("status", ""))
    priority = {"done": 3, "failed": 2, "claimed": 1, "pending": 0}.get(status, 0)
    return (priority, str(task_record["task"].get("task_id", "")), str(task_record["task"].get("worker_id", "")))


def _result_summary(task_record: dict | None) -> dict | None:
    if not task_record:
        return None

    task = task_record.get("task", {})
    result = task_record.get("result") or {}
    output = result.get("output") or {}
    notes = result.get("notes") or []
    worker_id = task.get("worker_id")

    if task_record.get("status") == "failed":
        summary = str(task_record.get("last_error") or "The task failed and needs recovery.")
        return {
            "taskId": task.get("task_id"),
            "workerId": worker_id,
            "taskType": task.get("task_type"),
            "status": "failed",
            "summary": summary,
            "outputKeys": [],
            "needsReview": True,
        }

    if not result:
        return None

    summary = None
    needs_review = False
    if notes:
        summary = "; ".join(str(note) for note in notes)
    elif "summary" in output:
        summary = str(output["summary"])
    elif "document" in output:
        summary = _truncate_inline(str(output["document"]))
    elif "steps" in output:
        summary = f"{len(output.get('steps', []))} planned steps are ready."
    elif "approved" in output:
        approved = bool(output.get("approved"))
        missing = output.get("missing") or []
        needs_review = not approved or bool(missing)
        if approved:
            summary = "Guardian says the thread is ready to continue."
        else:
            summary = "Guardian review still needs attention."
            if missing:
                summary += f" Missing: {', '.join(str(item) for item in missing)}."
    elif output:
        summary = f"Saved output with {len(output)} field{'s' if len(output) != 1 else ''}."

    if not summary:
        return None

    return {
        "taskId": task.get("task_id"),
        "workerId": worker_id,
        "taskType": task.get("task_type"),
        "status": result.get("status", task_record.get("status")),
        "summary": summary,
        "outputKeys": sorted(output.keys()),
        "needsReview": needs_review,
    }


def _needs_human_review(
    item: dict,
    *,
    state: str,
    latest_result: dict | None,
    latest_artifact: dict | None,
    review_status: str,
) -> bool:
    return bool(
        item.get("blocked_count")
        or item.get("failed_count")
        or item.get("expired_count")
        or ((latest_result and latest_result.get("needsReview")) and review_status != "reviewed")
        or ((state == "done" or state == "review-needed") and (latest_result or latest_artifact) and review_status != "reviewed")
    )


def _visual_state(
    state: str,
    needs_human_review: bool,
    *,
    review_status: str,
    latest_result: dict | None,
    latest_artifact: dict | None,
) -> str:
    if state == "blocked":
        return "blocked"
    if needs_human_review or state in {"failed", "review-needed"}:
        return "review-needed"
    if state == "reviewed":
        return "reviewed"
    if state == "ready":
        return "ready"
    if state == "running":
        return "running"
    if state == "done" and (latest_result or latest_artifact):
        return "review-needed"
    return "quiet"


def _resume_score(
    item: dict,
    *,
    latest_event: dict | None,
    latest_artifact: dict | None,
    latest_result: dict | None,
    state: str,
    needs_human_review: bool,
    event_recency: int,
    review_status: str,
) -> int:
    score = 0
    score += item.get("blocked_count", 0) * 170
    score += item.get("failed_count", 0) * 145
    score += item.get("expired_count", 0) * 125
    score += item.get("ready_count", 0) * 30
    score += item.get("claimed_count", 0) * 18
    score += item.get("task_counts", {}).get("done", 0) * 8
    score += _state_weight(state)
    if needs_human_review:
        score += 80
    if review_status == "reviewed":
        score += 65
    if latest_artifact:
        score += _artifact_score(latest_artifact)
    if latest_result:
        score += _result_score(latest_result)
    if latest_event:
        score += _event_score(latest_event)
        score += max(1, 10 - min(event_recency, 9))
    return score


def _state_weight(state: str) -> int:
    return {
        "blocked": 90,
        "failed": 70,
        "review-needed": 60,
        "reviewed": 40,
        "ready": 25,
        "running": 20,
        "done": 15,
        "quiet": 5,
    }.get(state, 0)


def _artifact_score(latest_artifact: dict) -> int:
    media_type = str(latest_artifact.get("mediaType", "")).lower()
    name = str(latest_artifact.get("name", "")).lower()
    if name.endswith(".md") or media_type == "text/markdown":
        return 155
    if media_type.startswith("text/"):
        return 130
    return 100


def _result_score(latest_result: dict) -> int:
    task_type = str(latest_result.get("taskType", "")).lower()
    output_keys = latest_result.get("outputKeys") or []
    base = {
        "draft": 150,
        "review": 135,
        "plan": 115,
        "summarize": 95,
    }.get(task_type, 90)
    if output_keys:
        base += min(len(output_keys) * 4, 16)
    return base


def _event_score(latest_event: dict) -> int:
    event_name = str(latest_event.get("event", "")).lower()
    return {
        "artifact_written": 30,
        "artifact_copied": 24,
        "completed": 22,
        "failed": 18,
        "reclaimed": 16,
        "released": 12,
        "claimed": 9,
        "enqueued": 4,
    }.get(event_name, 6)


def _resume_target(record: dict) -> dict:
    return {
        "threadId": record["threadId"],
        "title": record["title"],
        "nextAction": record["nextAction"],
        "whyNow": record["whyNow"],
        "resumeMode": record["resumeMode"],
        "latestWorkerEvent": record["latestWorkerEvent"],
        "latestArtifact": record["latestArtifact"],
        "latestResult": record["latestResult"],
        "reviewReceipt": record["reviewReceipt"],
        "reviewStatus": record["reviewStatus"],
        "needsHumanReview": record["needsHumanReview"],
        "actions": record["actions"],
        "visualState": record["visualState"],
        "visualAssetRefs": record["visualAssetRefs"],
        "projectUrl": record["projectUrl"],
        "state": record["state"],
        "detail": record["detail"],
    }


def _latest_review_receipt(
    thread_id: str,
    *,
    latest_artifact: dict | None,
    latest_result: dict | None,
    review_receipt_records: dict[str, list[dict]],
) -> dict | None:
    matches = []
    for receipt in review_receipt_records.get(thread_id, []):
        artifact_match = latest_artifact and receipt.get("artifact_id") == latest_artifact["artifactId"]
        result_match = latest_result and receipt.get("result_task_id") == latest_result["taskId"]
        if artifact_match or result_match:
            matches.append(receipt)

    if not matches:
        return None

    receipt = sorted(matches, key=lambda item: (str(item.get("created_at", "")), str(item.get("review_ref", ""))))[-1]
    return {
        "reviewRef": receipt.get("review_ref"),
        "artifactId": receipt.get("artifact_id"),
        "resultTaskId": receipt.get("result_task_id"),
        "status": receipt.get("status", "reviewed"),
        "createdAt": receipt.get("created_at"),
    }


def _review_status(
    latest_review_receipt: dict | None,
    *,
    latest_artifact: dict | None,
    latest_result: dict | None,
) -> str:
    if latest_review_receipt:
        return "reviewed"
    if latest_artifact or latest_result:
        return "pending"
    return "none"


def _truncate_inline(value: str, limit: int = 140) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
