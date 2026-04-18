from __future__ import annotations

from html import escape
import json


def render_project_board(workflows: list[dict]) -> str:
    cards = []
    for workflow in workflows:
        chips = _render_task_chips(workflow.get("task_counts", {})) or '<span class="chip">no tasks yet</span>'
        board_label = _board_state_label(workflow)
        board_detail = workflow.get("board_detail") or _board_fallback_detail(workflow)
        board_next_action = workflow.get("board_next_action") or {}
        next_action = board_next_action.get("text")
        action_row = _render_primary_board_action(board_next_action) + _render_board_actions(workflow.get("board_actions") or [])
        cards.append(
            "".join(
                [
                    '<article class="card">',
                    f"<h2>{escape(workflow.get('title', workflow['thread_id']))}</h2>",
                    f'<p class="muted"><code>{escape(workflow["thread_id"])}</code></p>',
                    f"<p>{escape(_truncate(workflow.get('objective', ''), 180))}</p>",
                    f'<p class="board-state"><span class="status-chip">{escape(board_label)}</span></p>',
                    f'<p class="muted">{escape(board_detail)}</p>',
                    f'<p class="next-action">{escape(next_action or "Open the project and take the next step from there.")}</p>',
                    f'<p class="muted">sources {workflow.get("source_count", 0)} · artifacts {workflow.get("artifact_count", 0)}</p>',
                    f'<div class="chips">{chips}</div>',
                    action_row,
                    f'<p><a href="/projects/research-writing/{escape(workflow["thread_id"])}/view">Open project</a></p>',
                    "</article>",
                ]
            )
        )

    workflow_html = "".join(cards) or '<article class="card"><h2>No projects yet</h2><p class="muted">Use the form to seed the first research/writing workflow.</p></article>'
    payload = _script_json({"workflows": workflows})
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Cloud Bridge Projects</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background: #0b1220; color: #e5eefb; }}
    a {{ color: #93c5fd; }}
    textarea, input {{ width: 100%; box-sizing: border-box; background: #0f172a; color: #e5eefb; border: 1px solid #334155; border-radius: 10px; padding: 10px; }}
    button {{ background: #0f766e; color: white; border: 0; border-radius: 999px; padding: 10px 16px; cursor: pointer; }}
    .grid {{ display: grid; grid-template-columns: minmax(300px, 420px) 1fr; gap: 18px; align-items: start; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
    .card {{ background: #111827; border: 1px solid #334155; border-radius: 14px; padding: 16px; }}
    .chips {{ margin-top: 10px; }}
    .chip {{ display: inline-block; margin: 0 8px 8px 0; padding: 6px 10px; background: #1e293b; border-radius: 999px; }}
    .muted {{ color: #94a3b8; }}
    .board-state {{ margin: 12px 0 4px; }}
    .status-chip {{ display: inline-block; padding: 6px 10px; background: #122235; color: #d8e7fb; border: 1px solid #294463; border-radius: 999px; }}
    .next-action {{ margin: 0; color: #dbe7f6; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 0; }}
    .action-link, .action-button {{ display: inline-flex; align-items: center; justify-content: center; font: inherit; border-radius: 999px; border: 1px solid #334155; padding: 8px 12px; text-decoration: none; }}
    .action-link {{ background: #1d4ed8; color: #eff6ff; }}
    .action-link.secondary, .action-button.secondary {{ background: #172033; color: #dbe7f6; }}
    .action-button {{ background: #0f766e; color: white; cursor: pointer; }}
    .help {{ font-size: 0.95rem; color: #cbd5e1; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <h1>Cloud Bridge Projects</h1>
  <p class=\"muted\">Zero-cost local intake for research/writing work on your private hub. <a href=\"/inbox\">Open inbox</a> · <a href=\"/drop-folders/view\">Open drop folders</a></p>
  <div class=\"grid\">
    <section class=\"card\">
      <h2>New Project</h2>
      <p class=\"help\">Paste one source path per line, or point at a whole folder already available on the server.</p>
      <form id=\"project-form\">
        <p><label>Title<br><input name=\"title\" required></label></p>
        <p><label>Objective<br><textarea name=\"objective\" rows=\"5\" required></textarea></label></p>
        <p><label>Source paths (one per line)<br><textarea name=\"sources\" rows=\"5\"></textarea></label></p>
        <p><label>Folder path (optional)<br><input name=\"folder\" placeholder=\"/runtime/drop/project-alpha\"></label></p>
        <p><label>Constraints (one per line)<br><textarea name=\"constraints\" rows=\"4\">local only\nzero cost</textarea></label></p>
        <p><button type=\"submit\">Create Project</button></p>
      </form>
      <pre id=\"status\" class=\"muted\"></pre>
    </section>
    <section>
      <div class=\"cards\">{workflow_html}</div>
    </section>
  </div>
  <script>
    window.__CLOUD_BRIDGE_PROJECTS__ = {escape(payload)};
    const form = document.getElementById('project-form');
    const status = document.getElementById('status');
    form.addEventListener('submit', async (event) => {{
      event.preventDefault();
      const data = new FormData(form);
      const sources = (data.get('sources') || '').split('\n').map(v => v.trim()).filter(Boolean);
      const constraints = (data.get('constraints') || '').split('\n').map(v => v.trim()).filter(Boolean);
      const folder = (data.get('folder') || '').trim();
      const payload = {{
        title: (data.get('title') || '').trim(),
        objective: (data.get('objective') || '').trim(),
        constraints,
      }};
      const endpoint = folder ? '/projects/research-writing/import-folder' : '/projects/research-writing/bootstrap';
      if (folder) payload.folder_path = folder;
      else payload.source_paths = sources;
      status.textContent = 'Creating project...';
      const response = await fetch(endpoint, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload),
      }});
      const body = await response.json();
      if (!response.ok) {{
        status.textContent = body.detail || JSON.stringify(body, null, 2);
        return;
      }}
      window.location.href = `/projects/research-writing/${{encodeURIComponent(body.thread_id)}}/view`;
    }});
    for (const button of document.querySelectorAll('[data-post-url]')) {{
      button.addEventListener('click', async () => {{
        status.textContent = 'Working...';
        const response = await fetch(button.dataset.postUrl, {{ method: 'POST' }});
        const body = await response.json();
        if (!response.ok) {{
          status.textContent = body.detail || JSON.stringify(body, null, 2);
          return;
        }}
        window.location.reload();
      }});
    }}
  </script>
</body>
</html>"""


def render_project_detail(project: dict) -> str:
    constraints = "".join(f"<li>{escape(item)}</li>" for item in project.get("constraints", [])) or "<li>none</li>"
    sources = "".join(
        f"<li><strong>{escape(source['name'])}</strong><br><span class=\"muted\">{escape(_truncate(source.get('excerpt', ''), 220))}</span></li>"
        for source in project.get("sources", [])
    ) or "<li>none</li>"
    tasks = "".join(
        "<tr>"
        f"<td>{escape(task['task']['worker_id'])}</td>"
        f"<td>{escape(task['task']['task_type'])}</td>"
        f"<td>{escape(task['status'])}</td>"
        f"<td>{escape(_task_note(task))}</td>"
        "</tr>"
        for task in project.get("tasks", [])
    ) or '<tr><td colspan="4">none</td></tr>'
    artifacts = "".join(
        "<tr>"
        f"<td><a href=\"/artifacts/{escape(artifact['artifact_id'])}\">{escape(artifact['name'])}</a></td>"
        f"<td>{escape(artifact['media_type'])}</td>"
        f"<td>{escape(str(artifact['size_bytes']))}</td>"
        "</tr>"
        for artifact in project.get("artifacts", [])
    ) or '<tr><td colspan="3">none</td></tr>'
    payload = _script_json({"thread_id": project["thread_id"]})
    latest_draft_artifact_id = project.get("latest_draft_artifact_id")
    latest_review_receipt = project.get("latest_review_receipt") or {}
    review_summary = _review_summary(latest_draft_artifact_id, latest_review_receipt)
    review_buttons = []
    review_controls_html = ""
    if latest_draft_artifact_id:
        selected_approved = " selected" if latest_review_receipt.get("verdict", "approved") != "revise" else ""
        selected_revise = " selected" if latest_review_receipt.get("verdict") == "revise" else ""
        review_note = escape(str(latest_review_receipt.get("note") or ""))
        review_controls_html = (
            '<div class="review-form">'
            '<label for="review-verdict">Review</label>'
            f'<select id="review-verdict"><option value="approved"{selected_approved}>Approved</option><option value="revise"{selected_revise}>Needs revision</option></select>'
            f'<input id="review-note" type="text" value="{review_note}" placeholder="Leave one short note if this needs a change." />'
            '<button id="save-review" class="secondary">Save Review</button>'
            '</div>'
        )
    if latest_review_receipt:
        continue_label = "Run Revision Pass" if latest_review_receipt.get("verdict") == "revise" else "Continue Thread"
        review_buttons.append(f'<button id="continue-thread">{continue_label}</button>')
    review_buttons_html = "".join(review_buttons)
    review_base_url = f"/projects/research-writing/{escape(project['thread_id'])}/review"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{escape(project.get('title', project['thread_id']))}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background: #0b1220; color: #e5eefb; }}
    a {{ color: #93c5fd; }}
    button {{ background: #1d4ed8; color: white; border: 0; border-radius: 999px; padding: 10px 16px; cursor: pointer; margin-right: 10px; }}
    button.secondary {{ background: #334155; }}
    input, select {{ font: inherit; }}
    .card {{ background: #111827; border: 1px solid #334155; border-radius: 14px; padding: 16px; margin-bottom: 16px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .chip {{ display: inline-block; margin: 0 8px 8px 0; padding: 6px 10px; background: #1e293b; border-radius: 999px; }}
    .review-form {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 14px 0 0; }}
    .review-form label {{ color: #cbd5e1; }}
    .review-form select, .review-form input {{ background: #0f172a; color: #e5eefb; border: 1px solid #334155; border-radius: 10px; padding: 10px 12px; }}
    .review-form input {{ min-width: min(360px, 100%); flex: 1 1 320px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #334155; vertical-align: top; }}
    .muted {{ color: #94a3b8; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <p><a href=\"/projects/research-writing/board\">Back to projects</a> · <a href=\"/drop-folders/view\">Drop folders</a></p>
  <h1>{escape(project.get('title', project['thread_id']))}</h1>
  <p class=\"muted\"><code>{escape(project['thread_id'])}</code></p>
    <div class=\"card\">
    <p>{escape(project.get('objective', ''))}</p>
    <div>{_render_task_chips(project.get('task_counts', {}))}</div>
    <p class=\"muted\">{escape(review_summary)}</p>
    {review_controls_html}
    <p>
      <button id=\"run-thread\">Run Thread</button>
      <button id=\"dispatch\">Run Dispatch</button>
      <button id=\"assemble\">Assemble Draft</button>
      {review_buttons_html}
    </p>
    <pre id=\"status\" class=\"muted\"></pre>
  </div>
  <div class=\"grid\">
    <section class=\"card\"><h2>Constraints</h2><ul>{constraints}</ul></section>
    <section class=\"card\"><h2>Sources</h2><ul>{sources}</ul></section>
  </div>
  <section class=\"card\">
    <h2>Tasks</h2>
    <table>
      <thead><tr><th>Worker</th><th>Task Type</th><th>Status</th><th>Result</th></tr></thead>
      <tbody>{tasks}</tbody>
    </table>
  </section>
  <section class=\"card\">
    <h2>Artifacts</h2>
    <table>
      <thead><tr><th>Name</th><th>Type</th><th>Bytes</th></tr></thead>
      <tbody>{artifacts}</tbody>
    </table>
  </section>
  <script>
    window.__CLOUD_BRIDGE_PROJECT__ = {escape(payload)};
    window.__CLOUD_BRIDGE_REVIEW__ = {{
      artifactId: {json.dumps(str(latest_draft_artifact_id or ""))},
      baseUrl: {json.dumps(review_base_url)},
    }};
    async function runAction(path) {{
      const status = document.getElementById('status');
      status.textContent = 'Working...';
      const response = await fetch(path, {{ method: 'POST' }});
      const body = await response.json();
      if (!response.ok) {{
        status.textContent = body.detail || JSON.stringify(body, null, 2);
        return;
      }}
      status.textContent = JSON.stringify(body, null, 2);
      window.location.reload();
    }}
    function buildReviewUrl() {{
      const params = new URLSearchParams();
      if (window.__CLOUD_BRIDGE_REVIEW__.artifactId) {{
        params.set('artifact_id', window.__CLOUD_BRIDGE_REVIEW__.artifactId);
      }}
      const verdict = document.getElementById('review-verdict')?.value || 'approved';
      params.set('verdict', verdict);
      const note = document.getElementById('review-note')?.value.trim();
      if (note) {{
        params.set('note', note);
      }}
      return `${{window.__CLOUD_BRIDGE_REVIEW__.baseUrl}}?${{params.toString()}}`;
    }}
    document.getElementById('run-thread').addEventListener('click', () => runAction(`/projects/research-writing/${{encodeURIComponent(window.__CLOUD_BRIDGE_PROJECT__.thread_id)}}/run?dispatch_limit=8&pass_limit=4`));
    document.getElementById('dispatch').addEventListener('click', () => runAction(`/projects/research-writing/${{encodeURIComponent(window.__CLOUD_BRIDGE_PROJECT__.thread_id)}}/dispatch?limit=4`));
    document.getElementById('assemble').addEventListener('click', () => runAction(`/projects/research-writing/${{encodeURIComponent(window.__CLOUD_BRIDGE_PROJECT__.thread_id)}}/assemble`));
    if (document.getElementById('save-review')) {{
      document.getElementById('save-review').addEventListener('click', () => runAction(buildReviewUrl()));
    }}
    if (document.getElementById('continue-thread')) {{
      document.getElementById('continue-thread').addEventListener('click', () => runAction(`/projects/research-writing/${{encodeURIComponent(window.__CLOUD_BRIDGE_PROJECT__.thread_id)}}/refresh`));
    }}
  </script>
</body>
</html>"""


def _render_task_chips(task_counts: dict) -> str:
    return "".join(
        f'<span class="chip"><strong>{escape(str(key))}</strong> {escape(str(value))}</span>'
        for key, value in sorted(task_counts.items())
    )


def _task_note(task: dict) -> str:
    result = task.get("result") or {}
    notes = result.get("notes") or []
    if notes:
        return "; ".join(str(note) for note in notes)
    output = result.get("output") or {}
    if "approved" in output:
        return f"Steward approved={output.get('approved')}"
    if "summary" in output:
        return _truncate(str(output.get("summary")), 120)
    if "document" in output:
        return _truncate(str(output.get("document")), 120)
    if "steps" in output:
        return f"{len(output.get('steps', []))} planned steps"
    return "-"


def _review_summary(latest_draft_artifact_id: str | None, latest_review_receipt: dict) -> str:
    if latest_review_receipt:
        created_at = latest_review_receipt.get("created_at", "a recent time")
        verdict = str(latest_review_receipt.get("verdict") or "approved")
        note = str(latest_review_receipt.get("note") or "").strip()
        prefix = "Latest draft reviewed locally" if verdict != "revise" else "Latest draft has requested changes saved locally"
        if note:
            return f"{prefix} at {created_at}. Note: {note}"
        return f"{prefix} at {created_at}."
    if latest_draft_artifact_id:
        return "Latest draft is waiting for a local review receipt."
    return "No draft has been produced yet."


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _board_state_label(workflow: dict) -> str:
    if workflow.get("needs_human_review"):
        return "Waiting for review"
    state = str(workflow.get("board_state") or "")
    review_status = str(workflow.get("review_status") or "")
    review_verdict = str((workflow.get("review_receipt") or {}).get("verdict") or "approved")
    if state == "reviewed":
        if review_verdict == "revise":
            return "Changes requested"
        return "Reviewed locally"
    if state == "ready" and review_status == "reviewed":
        if review_verdict == "revise":
            return "Revision ready"
        return "Ready to continue"
    if state == "ready":
        return "Ready to run"
    if state == "running":
        return "Running now"
    if state == "blocked":
        return "Blocked"
    if state == "failed":
        return "Needs recovery"
    if workflow.get("task_counts", {}).get("done"):
        return "Recent work saved"
    return "Getting started"


def _board_fallback_detail(workflow: dict) -> str:
    if workflow.get("task_counts", {}).get("done"):
        return "This thread already has finished work saved on the local hub."
    if workflow.get("task_count"):
        return "This thread has work in motion and can be opened from here."
    return "This project is ready for its first real pass."


def _render_board_actions(actions: list[dict]) -> str:
    items = []
    for action in actions[:2]:
        label = escape(str(action.get("label") or "Open"))
        class_suffix = " secondary" if action.get("tone") == "secondary" else ""
        href = action.get("href")
        post_url = action.get("postUrl")
        if href:
            items.append(f'<a class="action-link{class_suffix}" href="{escape(str(href))}">{label}</a>')
        elif post_url:
            items.append(
                f'<button type="button" class="action-button{class_suffix}" data-post-url="{escape(str(post_url))}">{label}</button>'
            )
    if not items:
        return ""
    return f'<div class="actions">{"".join(items)}</div>'


def _render_primary_board_action(action: dict) -> str:
    if not action:
        return ""
    label = action.get("label")
    href = action.get("href")
    post_url = action.get("postUrl")
    if not label or not (href or post_url):
        return ""
    return _render_board_actions(
        [
            {
                "label": label,
                "tone": "primary",
                "href": href,
                "postUrl": post_url,
            }
        ]
    )


def _script_json(value: object) -> str:
    return json.dumps(value).replace("</", "<\\/")
