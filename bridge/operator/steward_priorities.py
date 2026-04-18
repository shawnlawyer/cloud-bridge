from __future__ import annotations

_PRESERVE_ONE_NEXT_KINDS = {"approval", "bill"}


def continuity_one_next_step(resume_target: dict | None) -> dict | None:
    if not resume_target:
        return None

    title = str(resume_target.get("title") or "Resume work")
    why_now = str(resume_target.get("whyNow") or "")
    next_action = resume_target.get("nextAction") or {}
    actions = list(resume_target.get("actions") or [])
    review_receipt = resume_target.get("reviewReceipt") or {}
    review_verdict = str(review_receipt.get("verdict") or "approved")

    if resume_target.get("needsHumanReview"):
        text = f"Review {title} and mark it reviewed."
        kind = "continuity_review"
    elif resume_target.get("reviewStatus") == "reviewed" and resume_target.get("state") in {"reviewed", "ready"}:
        if review_verdict == "revise":
            text = f"Run the revision pass for {title}."
        else:
            text = f"Run the next pass for {title}."
        kind = "continuity_continue"
    elif resume_target.get("state") == "ready":
        text = f"Run the ready work for {title}."
        kind = "continuity_dispatch"
    else:
        text = str(next_action.get("text") or f"Open {title} and keep it moving.")
        kind = "continuity_resume"

    return {
        "kind": kind,
        "text": text,
        "detail": why_now or next_action.get("text") or "Resume the thread that is already lined up.",
        "context": f"Thread: {title}",
        "threadId": resume_target.get("threadId"),
        "projectUrl": resume_target.get("projectUrl"),
        "resumeMode": resume_target.get("resumeMode"),
        "actions": actions[:2],
    }


def prioritize_one_next_step(current: dict | None, resume_target: dict | None) -> dict:
    existing = dict(current or {})
    continuity_next = continuity_one_next_step(resume_target)
    if not continuity_next:
        return existing

    if str(existing.get("kind") or "").lower() in _PRESERVE_ONE_NEXT_KINDS and existing.get("text"):
        return existing

    return continuity_next
