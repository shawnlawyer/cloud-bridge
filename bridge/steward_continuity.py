from __future__ import annotations

from urllib.parse import quote

from bridge.inbox import build_inbox_state


def build_continuity_payload(store_root: str, task_limit: int = 20) -> dict:
    state = build_inbox_state(store_root, task_limit=task_limit)
    thread_rows = state.get("threads", [])
    records = [_thread_record(item) for item in thread_rows]
    summaries = [
        {
            "ref": item["ref"],
            "title": item["title"],
            "detail": item["detail"],
            "state": item["state"],
            "threadId": item["threadId"],
        }
        for item in records[:8]
    ]
    return {
        "schemaVersion": "steward-cloudbridge/v1",
        "operation": "records",
        "kind": "continuity",
        "summaries": summaries,
        "records": records,
    }


def _thread_record(item: dict) -> dict:
    thread_id = item["thread_id"]
    encoded_thread = quote(thread_id, safe="")
    parts = []
    if item.get("objective"):
        parts.append(item["objective"])
    counts = []
    if item.get("ready_count"):
        counts.append(f'{item["ready_count"]} ready')
    if item.get("blocked_count"):
        counts.append(f'{item["blocked_count"]} blocked')
    if item.get("failed_count"):
        counts.append(f'{item["failed_count"]} failed')
    if item.get("claimed_count"):
        counts.append(f'{item["claimed_count"]} running')
    done_count = item.get("task_counts", {}).get("done", 0)
    if done_count:
        counts.append(f"{done_count} done")
    if counts:
        parts.append(" · ".join(counts))

    return {
        "ref": f"continuity:{thread_id}",
        "threadId": thread_id,
        "title": item.get("title", thread_id),
        "detail": " — ".join(parts) if parts else "Project continuity available.",
        "state": _thread_state(item),
        "projectUrl": item.get("project_url"),
        "actions": _thread_actions(item, encoded_thread),
    }


def _thread_state(item: dict) -> str:
    if item.get("blocked_count"):
        return "blocked"
    if item.get("failed_count"):
        return "failed"
    if item.get("ready_count"):
        return "ready"
    if item.get("claimed_count"):
        return "running"
    if item.get("task_counts", {}).get("done"):
        return "done"
    return "quiet"


def _thread_actions(item: dict, encoded_thread: str) -> list[dict]:
    actions: list[dict] = []
    project_url = item.get("project_url")
    if project_url:
        actions.append({"label": "Open", "tone": "secondary", "href": project_url})

    if any(item.get(key) for key in ("ready_count", "blocked_count", "failed_count", "claimed_count")):
        actions.append(
            {
                "label": "Run thread",
                "tone": "primary",
                "postUrl": f"/projects/research-writing/{encoded_thread}/run?dispatch_limit=8&pass_limit=4",
            }
        )

    if item.get("ready_count"):
        actions.append(
            {
                "label": "Dispatch",
                "tone": "secondary",
                "postUrl": f"/inbox/dispatch?limit=4&thread_id={encoded_thread}",
            }
        )

    return actions
