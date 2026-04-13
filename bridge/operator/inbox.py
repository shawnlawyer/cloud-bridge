from __future__ import annotations

from html import escape
import json


def render_inbox_page(state: dict) -> str:
    summary = state.get("summary", {})
    threads = state.get("threads", [])
    ready_tasks = state.get("ready_tasks", [])
    blocked_tasks = state.get("blocked_tasks", [])
    failed_tasks = state.get("failed_tasks", [])
    claimed_tasks = state.get("claimed_tasks", [])

    summary_cards = "".join(
        f'<div class="card stat"><h2>{escape(label)}</h2><p>{escape(str(summary.get(key, 0)))}</p></div>'
        for key, label in (
            ("ready_count", "Ready"),
            ("blocked_count", "Blocked"),
            ("failed_count", "Failed"),
            ("claimed_count", "Claimed"),
            ("expired_count", "Expired Leases"),
            ("thread_count", "Threads"),
        )
    )
    threads_rows = "".join(_thread_row(item) for item in threads) or '<tr><td colspan="7">no threads yet</td></tr>'
    attention_rows = "".join(_task_row(item, mode="blocked") for item in blocked_tasks)
    attention_rows += "".join(_task_row(item, mode="failed") for item in failed_tasks)
    attention_rows += "".join(_task_row(item, mode="claimed") for item in claimed_tasks if item.get("expired"))
    attention_rows = attention_rows or '<tr><td colspan="7">nothing urgent right now</td></tr>'
    ready_rows = "".join(_task_row(item, mode="ready") for item in ready_tasks) or '<tr><td colspan="7">no ready tasks</td></tr>'

    payload = _script_json(state)
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Cloud Bridge Inbox</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background: #0b1220; color: #e5eefb; }}
    a {{ color: #93c5fd; }}
    button {{ background: #0f766e; color: white; border: 0; border-radius: 999px; padding: 10px 16px; cursor: pointer; margin-right: 10px; margin-bottom: 10px; }}
    button.secondary {{ background: #334155; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .card {{ background: #111827; border: 1px solid #334155; border-radius: 14px; padding: 16px; }}
    .stat p {{ font-size: 2rem; margin: 0; }}
    .section {{ margin-bottom: 18px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #334155; vertical-align: top; }}
    .muted {{ color: #94a3b8; }}
    .chips {{ margin-top: 8px; }}
    .chip {{ display: inline-block; margin: 0 8px 8px 0; padding: 5px 9px; background: #1e293b; border-radius: 999px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <p><a href=\"/operator/console\">Operator console</a> · <a href=\"/projects/research-writing/board\">Projects</a> · <a href=\"/drop-folders/view\">Drop folders</a></p>
  <h1>Cloud Bridge Inbox</h1>
  <p class=\"muted\">What needs attention now across the private hub.</p>
  <div>
    <button id=\"dispatch-global\">Run Next 4</button>
    <button id=\"reclaim\" class=\"secondary\">Reclaim Expired</button>
    <button id=\"maintain\" class=\"secondary\">Maintain Store</button>
  </div>
  <pre id=\"status\" class=\"muted\"></pre>
  <section class=\"stats\">{summary_cards}</section>
  <section class=\"card section\">
    <h2>Threads</h2>
    <table>
      <thead><tr><th>Thread</th><th>Queue</th><th>Blocked</th><th>Failed</th><th>Claimed</th><th>Counts</th><th>Actions</th></tr></thead>
      <tbody>{threads_rows}</tbody>
    </table>
  </section>
  <section class=\"card section\">
    <h2>Needs Attention</h2>
    <table>
      <thead><tr><th>Thread</th><th>Worker</th><th>Type</th><th>Status</th><th>Attempts</th><th>Reason</th><th>Open</th></tr></thead>
      <tbody>{attention_rows}</tbody>
    </table>
  </section>
  <section class=\"card section\">
    <h2>Ready Queue</h2>
    <table>
      <thead><tr><th>Thread</th><th>Worker</th><th>Type</th><th>Status</th><th>Attempts</th><th>Reason</th><th>Open</th></tr></thead>
      <tbody>{ready_rows}</tbody>
    </table>
  </section>
  <script>
    window.__CLOUD_BRIDGE_INBOX__ = {payload};
    async function post(path) {{
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
    document.getElementById('dispatch-global').addEventListener('click', () => post('/inbox/dispatch?limit=4'));
    document.getElementById('reclaim').addEventListener('click', () => post('/inbox/reclaim'));
    document.getElementById('maintain').addEventListener('click', () => post('/inbox/maintain'));
    for (const button of document.querySelectorAll('[data-thread-run]')) {{
      button.addEventListener('click', () => post(`/projects/research-writing/${{encodeURIComponent(button.dataset.threadRun)}}/run?dispatch_limit=8&pass_limit=4`));
    }}
    for (const button of document.querySelectorAll('[data-thread-dispatch]')) {{
      button.addEventListener('click', () => post(`/inbox/dispatch?limit=4&thread_id=${{encodeURIComponent(button.dataset.threadDispatch)}}`));
    }}
  </script>
</body>
</html>"""


def _thread_row(item: dict) -> str:
    chips = "".join(
        f'<span class="chip"><strong>{escape(str(key))}</strong> {escape(str(value))}</span>'
        for key, value in sorted(item.get("task_counts", {}).items())
    ) or '<span class="chip">none</span>'
    open_link = f'<a href="{escape(item["project_url"])}">Open</a>' if item.get("project_url") else "-"
    action_parts = []
    if item.get("ready_count"):
        action_parts.append(f'<button data-thread-run="{escape(item["thread_id"])}">Run Thread</button>')
        action_parts.append(f'<button data-thread-dispatch="{escape(item["thread_id"])}">Run 4</button>')
    action_button = "".join(action_parts) or "-"
    return (
        "<tr>"
        f"<td><strong>{escape(item['title'])}</strong><br><span class=\"muted\"><code>{escape(item['thread_id'])}</code></span></td>"
        f"<td>{escape(str(item.get('ready_count', 0)))}</td>"
        f"<td>{escape(str(item.get('blocked_count', 0)))}</td>"
        f"<td>{escape(str(item.get('failed_count', 0)))}</td>"
        f"<td>{escape(str(item.get('claimed_count', 0)))}</td>"
        f"<td>{chips}</td>"
        f"<td>{open_link}<br>{action_button}</td>"
        "</tr>"
    )


def _task_row(item: dict, mode: str) -> str:
    if mode == "blocked":
        reason = item.get("blocked_reason") or "blocked"
        status = "blocked"
    elif mode == "failed":
        reason = item.get("last_error") or "failed"
        status = "failed"
    elif mode == "claimed":
        expiry = item.get("lease_expires_at") or "lease open"
        reason = f"expired lease at {expiry}" if item.get("expired") else expiry
        status = "claimed"
    else:
        reason = "ready"
        status = item.get("status", "pending")
    open_link = f'<a href="{escape(item["project_url"])}">Open</a>' if item.get("project_url") else "-"
    return (
        "<tr>"
        f"<td>{escape(item['thread_title'])}</td>"
        f"<td>{escape(item['worker_label'])}</td>"
        f"<td>{escape(item['task_type'])}</td>"
        f"<td>{escape(status)}</td>"
        f"<td>{escape(str(item['attempt']))}/{escape(str(item['max_attempts']))}</td>"
        f"<td>{escape(reason)}</td>"
        f"<td>{open_link}</td>"
        "</tr>"
    )


def _script_json(value: object) -> str:
    return json.dumps(value).replace("</", "<\\/")
