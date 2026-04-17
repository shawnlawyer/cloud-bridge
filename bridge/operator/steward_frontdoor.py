from __future__ import annotations

from html import escape
import json

LANES = [
    ("bills", "Bills"),
    ("routines", "Routines"),
    ("important_dates", "Dates"),
    ("tasks", "Tasks"),
    ("rooms", "Rooms"),
    ("tools", "Tools"),
    ("notification_events", "Notifications"),
    ("approvals", "Approvals"),
]


def render_steward_frontdoor(home: dict, approvals: dict | None = None) -> str:
    one_next_step = home.get("oneNextStep", {})
    snapshot = home.get("todaySnapshot", {})
    current_context = home.get("currentContext", {})
    last_worked = home.get("lastWorked", {})
    approval_summaries = (approvals or {}).get("summaries", [])
    lane_cards = "".join(
        f'''<a class="lane-card" href="/steward/view/{escape(kind)}"><strong>{escape(label)}</strong><span>Open lane</span></a>'''
        for kind, label in LANES
    )
    approval_items = "".join(_approval_item(item) for item in approval_summaries) or '<li class="empty">No pending approvals.</li>'
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>One Next Step</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background: #08111f; color: #e7eef9; }}
    a {{ color: #93c5fd; text-decoration: none; }}
    .shell {{ max-width: 1100px; margin: 0 auto; }}
    .hero {{ display: grid; gap: 16px; grid-template-columns: 2fr 1fr; align-items: start; }}
    .panel {{ background: #111827; border: 1px solid #334155; border-radius: 18px; padding: 18px; }}
    .eyebrow {{ color: #8fb3d9; text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.75rem; }}
    h1, h2, h3 {{ margin: 0 0 0.4rem; }}
    .lead {{ font-size: 1.3rem; line-height: 1.5; margin: 0.6rem 0 0; }}
    .muted {{ color: #94a3b8; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-top: 16px; }}
    .stat {{ background: #0b1220; border-radius: 14px; padding: 14px; border: 1px solid #22324a; }}
    .stat strong {{ display: block; font-size: 1.6rem; margin-top: 6px; }}
    .composer {{ display: grid; grid-template-columns: 1fr auto; gap: 10px; margin-top: 16px; }}
    input, button {{ font: inherit; border-radius: 12px; border: 1px solid #334155; }}
    input {{ background: #0b1220; color: #e7eef9; padding: 12px 14px; }}
    button {{ background: #0f766e; color: white; padding: 12px 18px; cursor: pointer; }}
    button.secondary {{ background: #1e293b; }}
    .lane-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-top: 18px; }}
    .lane-card {{ display: flex; flex-direction: column; gap: 6px; background: #0b1220; border: 1px solid #22324a; border-radius: 14px; padding: 14px; }}
    .strip-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .strip-item {{ background: #0b1220; border: 1px solid #22324a; border-radius: 14px; padding: 14px; }}
    .context-list, .approval-list {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; }}
    .approval-item {{ background: #0b1220; border: 1px solid #22324a; border-radius: 14px; padding: 14px; }}
    .approval-actions {{ display: flex; gap: 8px; margin-top: 10px; }}
    .empty {{ color: #94a3b8; }}
    pre {{ white-space: pre-wrap; word-break: break-word; color: #cbd5e1; }}
    @media (max-width: 900px) {{ .hero {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <p class="muted"><a href="/operator/console">Operator console</a> · <a href="/inbox">Inbox</a> · <a href="/projects/research-writing/board">Projects</a> · <a href="/drop-folders/view">Drop folders</a></p>
    <div class="hero">
      <section class="panel">
        <div class="eyebrow">One Next Step</div>
        <h1>{escape(home.get("title", "One Next Step"))}</h1>
        <p class="lead">{escape(one_next_step.get("text", "Nothing queued yet."))}</p>
        <p class="muted">Heartbeat: {escape(home.get("heartbeat", "HEARTBEAT_OK"))}</p>
        <form id="ingest-form" class="composer">
          <input id="ingest-text" name="text" placeholder="Add bill mortgage due 1st" value="" />
          <button type="submit">Save</button>
        </form>
        <pre id="status" class="muted"></pre>
        <div class="lane-grid">{lane_cards}</div>
      </section>
      <section class="panel">
        <h2>Today</h2>
        <div class="stats">
          {_stat_card('Pending approvals', snapshot.get('pendingApprovalCount', 0))}
          {_stat_card('Overdue bills', snapshot.get('overdueBillCount', 0))}
          {_stat_card('Due routines', snapshot.get('dueRoutineCount', 0))}
          {_stat_card('Upcoming dates', snapshot.get('upcomingDateCount', 0))}
          {_stat_card('Active tasks', snapshot.get('activeTaskCount', 0))}
          {_stat_card('Active rooms', snapshot.get('activeRoomCount', 0))}
        </div>
      </section>
    </div>
    <section class="panel" style="margin-top: 18px;">
      <h2>Last Worked</h2>
      <div class="strip-grid">
        {_last_worked_item('Task', last_worked.get('task'))}
        {_last_worked_item('Room', last_worked.get('room'))}
        {_last_worked_item('Notification', last_worked.get('notification'))}
        {_last_worked_item('Worker', last_worked.get('workerEvent'))}
      </div>
    </section>
    <section class="panel" style="margin-top: 18px;">
      <h2>Current Context</h2>
      <ul class="context-list">
        {_context_item('Active task', _task_context(current_context.get('activeTask')))}
        {_context_item('Active room', _room_context(current_context.get('activeRoom')))}
        {_context_item('Cash pressure', _cash_context(current_context.get('cashPressure')))}
        {_context_item('Latest state', _state_context(current_context.get('latestState')))}
      </ul>
    </section>
    <section class="panel" style="margin-top: 18px;">
      <h2>Pending Approvals</h2>
      <ul class="approval-list">{approval_items}</ul>
    </section>
  </div>
  <script>
    window.__CLOUD_BRIDGE_HOME__ = {_script_json(home)};
    window.__CLOUD_BRIDGE_APPROVALS__ = {_script_json(approvals or {})};
    async function postJson(path, body) {{
      const response = await fetch(path, {{
        method: 'POST',
        headers: {{ 'content-type': 'application/json' }},
        body: JSON.stringify(body),
      }});
      const payload = await response.json();
      if (!response.ok) {{
        throw new Error(payload.detail || JSON.stringify(payload));
      }}
      return payload;
    }}
    document.getElementById('ingest-form').addEventListener('submit', async (event) => {{
      event.preventDefault();
      const status = document.getElementById('status');
      const text = document.getElementById('ingest-text').value;
      status.textContent = 'Saving...';
      try {{
        const payload = await postJson('/steward/ingest', {{ text }});
        status.textContent = payload.result?.message || 'Saved.';
        window.location.reload();
      }} catch (error) {{
        status.textContent = error.message;
      }}
    }});
    for (const button of document.querySelectorAll('[data-approval-ref]')) {{
      button.addEventListener('click', async () => {{
        const status = document.getElementById('status');
        status.textContent = 'Saving decision...';
        try {{
          const payload = await postJson('/steward/approval', {{
            approval_ref: button.dataset.approvalRef,
            decision: button.dataset.decision,
          }});
          status.textContent = payload.result?.status || 'Updated.';
          window.location.reload();
        }} catch (error) {{
          status.textContent = error.message;
        }}
      }});
    }}
  </script>
</body>
</html>'''


def render_steward_lane(title: str, payload: dict) -> str:
    summaries = payload.get("summaries", [])
    records = payload.get("records", [])
    kind = str(payload.get("kind", "")).lower()
    rows = "".join(
        f"<li><strong>{escape(str(item.get('title', item.get('ref', 'record'))))}</strong><br><span class=\"muted\">{escape(str(item.get('detail', '')))}</span></li>"
        for item in summaries
    ) or '<li class="empty">Nothing here yet.</li>'
    record_cards = "".join(_lane_record_item(kind, item) for item in records) or '<li class="empty">Nothing here yet.</li>'
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background: #08111f; color: #e7eef9; }}
    a {{ color: #93c5fd; text-decoration: none; }}
    .shell {{ max-width: 1000px; margin: 0 auto; }}
    .panel {{ background: #111827; border: 1px solid #334155; border-radius: 18px; padding: 18px; margin-bottom: 18px; }}
    .muted {{ color: #94a3b8; }}
    ul {{ list-style: none; padding: 0; display: grid; gap: 12px; }}
    li {{ background: #0b1220; border: 1px solid #22324a; border-radius: 14px; padding: 14px; }}
    .record-actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    button {{ font: inherit; border-radius: 10px; border: 1px solid #334155; background: #0f766e; color: white; padding: 8px 12px; cursor: pointer; }}
    button.secondary {{ background: #1e293b; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #0b1220; border: 1px solid #22324a; border-radius: 14px; padding: 14px; overflow-x: auto; }}
  </style>
</head>
<body>
  <div class="shell">
    <p class="muted"><a href="/">Back to One Next Step</a></p>
    <section class="panel">
      <h1>{escape(title)}</h1>
      <p class="muted">Default lane for the UI.</p>
      <ul>{rows}</ul>
    </section>
    <section class="panel">
      <h2>Operate Lane</h2>
      <ul>{record_cards}</ul>
      <pre id="status" class="muted"></pre>
    </section>
    <section class="panel">
      <h2>Structured Records</h2>
      <pre>{escape(json.dumps(records, indent=2))}</pre>
    </section>
  </div>
  <script>
    async function postJson(path, body) {{
      const response = await fetch(path, {{
        method: 'POST',
        headers: {{ 'content-type': 'application/json' }},
        body: JSON.stringify(body),
      }});
      const payload = await response.json();
      if (!response.ok) {{
        throw new Error(payload.detail || JSON.stringify(payload));
      }}
      return payload;
    }}
    for (const button of document.querySelectorAll('[data-record-action]')) {{
      button.addEventListener('click', async () => {{
        const status = document.getElementById('status');
        status.textContent = 'Saving...';
        try {{
          const payload = await postJson('/steward/action', {{
            kind: button.dataset.kind,
            ref: button.dataset.recordRef,
            action: button.dataset.recordAction,
          }});
          status.textContent = payload.result?.detail || payload.result?.status || 'Updated.';
          window.location.reload();
        }} catch (error) {{
          status.textContent = error.message;
        }}
      }});
    }}
  </script>
</body>
</html>'''


def _stat_card(label: str, value: object) -> str:
    return f'<div class="stat"><span class="muted">{escape(label)}</span><strong>{escape(str(value))}</strong></div>'


def _context_item(label: str, detail: str) -> str:
    return f'<li><strong>{escape(label)}</strong><br><span class="muted">{escape(detail)}</span></li>'


def _task_context(task: dict | None) -> str:
    if not task:
        return 'No active task.'
    return f"{task.get('label', 'Task')} · {task.get('track', 'general')}"


def _room_context(room: dict | None) -> str:
    if not room:
        return 'No active room recovery.'
    return f"{room.get('roomName', 'Room')} · {room.get('mode', 'standard')}"


def _cash_context(cash: dict | None) -> str:
    if not cash:
        return 'No cash signal yet.'
    return str(cash.get('text', 'No cash signal yet.'))


def _state_context(state: dict | None) -> str:
    if not state:
        return 'No recent state logged.'
    detail = state.get('detail')
    return state.get('state', 'steady') if not detail else f"{state.get('state', 'steady')} · {detail}"


def _approval_item(item: dict) -> str:
    ref = escape(str(item.get('ref', '')))
    detail = escape(str(item.get('detail', 'Needs a decision.')))
    title = escape(str(item.get('title', 'Approval')))
    return (
        '<li class="approval-item">'
        f'<strong>{title}</strong><br><span class="muted">{detail}</span>'
        f'<div class="approval-actions"><button data-approval-ref="{ref}" data-decision="approve">Approve</button>'
        f'<button class="secondary" data-approval-ref="{ref}" data-decision="deny">Deny</button></div>'
        '</li>'
    )


def _last_worked_item(label: str, item: dict | None) -> str:
    if not item:
        return f'<div class="strip-item"><strong>{escape(label)}</strong><br><span class="muted">Nothing recent.</span></div>'
    title = item.get("label") or item.get("title") or item.get("event") or "Recent"
    detail = item.get("detail") or item.get("status") or "Recent activity."
    return (
        f'<div class="strip-item"><strong>{escape(label)}</strong><br>'
        f'{escape(str(title))}<br><span class="muted">{escape(str(detail))}</span></div>'
    )


def _lane_record_item(kind: str, item: dict) -> str:
    title = (
        item.get("title")
        or item.get("label")
        or item.get("name")
        or item.get("roomName")
        or item.get("toolName")
        or item.get("ref")
        or "Record"
    )
    detail = (
        item.get("detail")
        or item.get("continuity")
        or item.get("recoveryPrompt")
        or item.get("amountText")
        or item.get("location")
        or item.get("state")
        or ""
    )
    ref = str(item.get("ref") or item.get("approvalRef") or item.get("notificationRef") or "")
    actions = item.get("actions", [])
    action_buttons = _record_actions(kind, ref, actions)
    return (
        "<li>"
        f"<strong>{escape(str(title))}</strong><br><span class=\"muted\">{escape(str(detail))}</span>"
        f"{action_buttons}"
        "</li>"
    )


def _record_actions(kind: str, record_ref: str, actions: list[dict]) -> str:
    if not actions or not record_ref:
        return ""
    buttons = "".join(
        f'<button class="{escape(str(action.get("tone", "primary")))}" data-kind="{escape(kind)}" '
        f'data-record-ref="{escape(record_ref)}" data-record-action="{escape(str(action.get("action", "")))}">'
        f'{escape(str(action.get("label", action.get("action", "Run"))))}</button>'
        for action in actions
    )
    return f'<div class="record-actions">{buttons}</div>'


def _script_json(value: object) -> str:
    return json.dumps(value).replace('</', '<\\/')
