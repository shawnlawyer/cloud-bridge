from __future__ import annotations

from html import escape
import json

LANES = [
    ("bills", "Bills"),
    ("followups", "Follow-ups"),
    ("routines", "Routines"),
    ("important_dates", "Dates"),
    ("tasks", "Tasks"),
    ("rooms", "Rooms"),
    ("tools", "Tools"),
    ("continuity", "Continuity"),
    ("notification_events", "Notifications"),
    ("approvals", "Approvals"),
]


def render_steward_frontdoor(home: dict, approvals: dict | None = None) -> str:
    one_next_step = home.get("oneNextStep", {})
    resume_target = home.get("resumeTarget") or (home.get("continuity") or {}).get("resumeTarget") or {}
    snapshot = home.get("todaySnapshot", {})
    current_context = home.get("currentContext", {})
    last_worked = home.get("lastWorked", {})
    steward_last_worked = last_worked.get("steward") or _steward_last_worked_fallback(last_worked.get("notification"), one_next_step)
    resume_last_worked = last_worked.get("resume") or _resume_last_worked_fallback(resume_target, last_worked.get("workerEvent"))
    schedule = home.get("schedule", {})
    continuity = (home.get("continuity") or {}).get("records", [])
    approval_summaries = (approvals or {}).get("summaries", [])
    lane_cards = "".join(
        f'''<a class="lane-card" href="/steward/view/{escape(kind)}"><strong>{escape(label)}</strong><span>See what is waiting</span></a>'''
        for kind, label in LANES
    )
    approval_items = "".join(_approval_item(item) for item in approval_summaries) or '<li class="empty">No pending approvals.</li>'
    continuity_tail = continuity[1:4] if resume_target else continuity[:3]
    continuity_items = "".join(_continuity_item(item) for item in continuity_tail) or '<li class="empty">Nothing else is waiting right now.</li>'
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>One Next Step</title>
  <style>
    :root {{
      --ink: #edf5f2;
      --muted: #b6c6c0;
      --line: rgba(191, 212, 196, 0.20);
      --accent: #e8b96d;
      --accent-strong: #ec8f45;
      --panel: rgba(8, 20, 29, 0.78);
      --panel-soft: rgba(12, 29, 41, 0.62);
      --shadow: 0 28px 70px rgba(0, 0, 0, 0.22);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      background:
        radial-gradient(circle at top left, rgba(245, 220, 170, 0.20), transparent 34%),
        radial-gradient(circle at top right, rgba(111, 164, 148, 0.18), transparent 30%),
        linear-gradient(180deg, #0a1620 0%, #132733 52%, #0b141c 100%);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, sans-serif;
    }}
    a {{ color: #dbeee5; text-decoration: none; }}
    .shell {{ max-width: 1180px; margin: 0 auto; }}
    .topline {{ color: var(--muted); margin: 0 0 18px; font-size: 0.95rem; display: flex; flex-wrap: wrap; gap: 12px; }}
    .hero {{ display: grid; gap: 18px; grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr); align-items: stretch; }}
    .split {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 18px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 28px;
      padding: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }}
    .panel.soft {{ background: var(--panel-soft); }}
    .eyebrow {{
      color: #f4d5a1;
      letter-spacing: 0.11em;
      font-size: 0.77rem;
      text-transform: uppercase;
    }}
    h1, h2, h3 {{ margin: 0; }}
    h1 {{ font-size: clamp(2rem, 4vw, 3.4rem); line-height: 1.02; margin-top: 10px; max-width: 12ch; }}
    h2 {{ margin-bottom: 0.45rem; font-size: 1.35rem; }}
    .lead {{ font-size: 1.18rem; line-height: 1.55; margin: 18px 0 0; max-width: 34rem; }}
    .muted {{ color: var(--muted); }}
    .hero-copy {{ display: flex; flex-direction: column; min-height: 100%; }}
    .one-next-detail {{ margin-top: 12px; max-width: 34rem; }}
    .heartbeat {{ margin-top: auto; padding-top: 20px; color: #c7d6d0; }}
    .composer {{ display: grid; grid-template-columns: 1fr auto; gap: 10px; margin-top: 20px; }}
    input, button {{ font: inherit; border-radius: 14px; border: 1px solid var(--line); }}
    input {{ background: rgba(7, 17, 24, 0.8); color: var(--ink); padding: 14px 16px; }}
    button {{ background: linear-gradient(180deg, #e29d54 0%, #d2783b 100%); color: #fffdf8; padding: 12px 18px; cursor: pointer; }}
    button.secondary, .action-link.secondary {{ background: rgba(18, 34, 45, 0.82); }}
    .status-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 14px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(240, 190, 113, 0.12);
      color: #f4d7a6;
      border: 1px solid rgba(240, 190, 113, 0.18);
      font-size: 0.95rem;
    }}
    .resume-panel {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 0.95fr);
      gap: 18px;
      overflow: hidden;
      min-height: 100%;
    }}
    .resume-copy {{ display: flex; flex-direction: column; gap: 12px; }}
    .resume-copy .title {{ font-size: clamp(1.6rem, 3vw, 2.7rem); line-height: 1.03; max-width: 14ch; }}
    .resume-next {{ font-size: 1.12rem; line-height: 1.5; margin: 0; max-width: 32rem; }}
    .resume-why {{ margin: 0; color: #d4dfda; }}
    .resume-facts {{ display: grid; gap: 12px; margin-top: 8px; }}
    .fact {{ padding: 14px; border-radius: 18px; background: rgba(6, 16, 22, 0.42); border: 1px solid rgba(255, 255, 255, 0.08); }}
    .fact strong {{ display: block; margin-bottom: 6px; color: #f8ead0; font-size: 0.93rem; }}
    .fact-line {{ color: var(--muted); font-size: 0.95rem; }}
    .resume-visual {{
      position: relative;
      min-height: 360px;
      border-radius: 24px;
      overflow: hidden;
      background: rgba(2, 9, 14, 0.54);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .resume-visual img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .visual-caption {{
      position: absolute;
      left: 16px;
      right: 16px;
      bottom: 16px;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 14px;
      border-radius: 18px;
      background: rgba(6, 15, 22, 0.72);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .caption-copy strong, .caption-copy span {{ display: block; }}
    .caption-copy span {{ color: var(--muted); font-size: 0.92rem; margin-top: 4px; }}
    .button-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-top: 16px; }}
    .stat {{ background: rgba(7, 17, 24, 0.58); border-radius: 18px; padding: 16px; border: 1px solid rgba(255, 255, 255, 0.06); }}
    .stat strong {{ display: block; font-size: 1.55rem; margin-top: 6px; }}
    .strip-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .strip-item {{ background: rgba(7, 17, 24, 0.58); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 18px; padding: 14px; }}
    .lane-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 18px; }}
    .lane-card {{ display: flex; flex-direction: column; gap: 6px; background: rgba(7, 17, 24, 0.58); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 18px; padding: 14px; }}
    .lane-card span {{ color: var(--muted); }}
    .context-list, .approval-list, .continuity-list {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; }}
    .approval-item {{ background: rgba(7, 17, 24, 0.58); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 18px; padding: 14px; }}
    .approval-actions {{ display: flex; gap: 8px; margin-top: 10px; }}
    .record-actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .action-link {{ display: inline-flex; align-items: center; justify-content: center; font: inherit; border-radius: 12px; border: 1px solid var(--line); background: linear-gradient(180deg, #e29d54 0%, #d2783b 100%); color: #fffdf8; padding: 9px 13px; cursor: pointer; }}
    .empty {{ color: #94a3b8; }}
    pre {{ white-space: pre-wrap; word-break: break-word; color: #cbd5e1; }}
    @media (max-width: 980px) {{
      .hero, .split, .resume-panel {{ grid-template-columns: 1fr; }}
      .resume-visual {{ min-height: 280px; }}
    }}
    @media (max-width: 720px) {{
      body {{ padding: 16px; }}
      .composer {{ grid-template-columns: 1fr; }}
      .topline {{ font-size: 0.88rem; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <p class="topline"><a href="/operator/console">Operator console</a> · <a href="/inbox">Inbox</a> · <a href="/projects/research-writing/board">Projects</a> · <a href="/drop-folders/view">Drop folders</a></p>
    <div class="hero">
      <section class="panel soft">
        <div class="hero-copy">
          <div class="eyebrow">One Next Step</div>
          <h1>{escape(home.get("title", "One Next Step"))}</h1>
          <p class="lead">{escape(one_next_step.get("text", "Nothing queued yet."))}</p>
          {_one_next_detail(one_next_step)}
          {_one_next_actions(one_next_step)}
          <div class="status-pill">{escape(home.get("state", {}).get("label", "steady").replace('-', ' ').title())}</div>
          <form id="ingest-form" class="composer">
            <input id="ingest-text" name="text" placeholder="Add bill mortgage due 1st" value="" />
            <button type="submit">Save</button>
          </form>
          <pre id="status" class="muted"></pre>
          <p class="heartbeat">Heartbeat: {escape(home.get("heartbeat", "HEARTBEAT_OK"))}</p>
        </div>
      </section>
      <section class="panel">
        {_resume_panel(resume_target)}
      </section>
    </div>
    <section class="panel" style="margin-top: 18px;">
      <h2>Today</h2>
      <div class="stats">
        {_stat_card('Pending approvals', snapshot.get('pendingApprovalCount', 0))}
        {_stat_card('Overdue bills', snapshot.get('overdueBillCount', 0))}
        {_stat_card('Due follow-ups', snapshot.get('dueFollowupCount', 0))}
        {_stat_card('Due routines', snapshot.get('dueRoutineCount', 0))}
        {_stat_card('Upcoming dates', snapshot.get('upcomingDateCount', 0))}
        {_stat_card('Active tasks', snapshot.get('activeTaskCount', 0))}
        {_stat_card('Active rooms', snapshot.get('activeRoomCount', 0))}
        {_stat_card('Continuity items', snapshot.get('continuityCount', 0))}
      </div>
    </section>
    <section class="panel" style="margin-top: 18px;">
      <h2>Last Worked</h2>
      <div class="strip-grid">
        {_last_worked_item('Task', last_worked.get('task'))}
        {_last_worked_item('Room', last_worked.get('room'))}
        {_last_worked_item('Steward', steward_last_worked)}
        {_last_worked_item('Resume', resume_last_worked)}
      </div>
    </section>
    <div class="split">
      <section class="panel">
        <h2>Current Context</h2>
        <ul class="context-list">
          {_context_item('Active task', _task_context(current_context.get('activeTask')))}
          {_context_item('Active room', _room_context(current_context.get('activeRoom')))}
          {_context_item('Cash pressure', _cash_context(current_context.get('cashPressure')))}
          {_context_item('Latest state', _state_context(current_context.get('latestState')))}
        </ul>
      </section>
      <section class="panel">
        <h2>Continue Work</h2>
        <ul class="continuity-list">{continuity_items}</ul>
      </section>
    </div>
    <div class="split">
      <section class="panel">
        <h2>Rhythm</h2>
        <p class="muted">{escape(_schedule_summary(schedule))}</p>
        <div class="button-row">
          <button data-tick-mode="heartbeat">Run heartbeat</button>
          <button data-tick-mode="morning">Run morning</button>
          <button data-tick-mode="midday">Run midday</button>
          <button data-tick-mode="evening">Run evening</button>
          <button class="secondary" data-tick-mode="bills">Run bills</button>
          <button class="secondary" data-tick-mode="followups">Run follow-ups</button>
          <button class="secondary" data-tick-mode="dates">Run dates</button>
        </div>
      </section>
      <section class="panel">
        <h2>Pending Approvals</h2>
        <ul class="approval-list">{approval_items}</ul>
      </section>
    </div>
    <section class="panel" style="margin-top: 18px;">
      <h2>Open a lane</h2>
      <div class="lane-grid">{lane_cards}</div>
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
    for (const button of document.querySelectorAll('[data-tick-mode]')) {{
      button.addEventListener('click', async () => {{
        const status = document.getElementById('status');
        status.textContent = 'Running tick...';
        try {{
          const payload = await postJson('/steward/tick', {{
            mode: button.dataset.tickMode,
          }});
          status.textContent = payload.result?.runs?.map((run) => `${{run.mode}}: ${{run.status}}`).join(', ') || 'Tick complete.';
          window.location.reload();
        }} catch (error) {{
          status.textContent = error.message;
        }}
      }});
    }}
    for (const button of document.querySelectorAll('[data-post-url]')) {{
      button.addEventListener('click', async () => {{
        const status = document.getElementById('status');
        status.textContent = 'Running...';
        try {{
          await fetch(button.dataset.postUrl, {{ method: 'POST' }});
          status.textContent = 'Done.';
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
    button.secondary, .action-link.secondary {{ background: #1e293b; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #0b1220; border: 1px solid #22324a; border-radius: 14px; padding: 14px; overflow-x: auto; }}
    .action-link {{ display: inline-flex; align-items: center; justify-content: center; font: inherit; border-radius: 10px; border: 1px solid #334155; background: #0f766e; color: white; padding: 8px 12px; cursor: pointer; }}
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
    for (const button of document.querySelectorAll('[data-post-url]')) {{
      button.addEventListener('click', async () => {{
        const status = document.getElementById('status');
        status.textContent = 'Running...';
        try {{
          await fetch(button.dataset.postUrl, {{ method: 'POST' }});
          status.textContent = 'Done.';
          window.location.reload();
        }} catch (error) {{
          status.textContent = error.message;
        }}
      }});
    }}
  </script>
</body>
</html>'''


def _one_next_detail(one_next_step: dict) -> str:
    detail = one_next_step.get('detail')
    if not detail:
        return ''
    return f'<p class="one-next-detail muted">{escape(str(detail))}</p>'


def _one_next_actions(one_next_step: dict) -> str:
    actions = one_next_step.get('actions') or []
    if not actions:
        return ''
    action_kind = str(one_next_step.get('actionKind') or one_next_step.get('kind') or '')
    record_ref = str(one_next_step.get('ref') or one_next_step.get('approvalRef') or '')
    return _record_actions(action_kind, record_ref, actions)


def _resume_panel(resume_target: dict) -> str:
    if not resume_target:
        return (
            '<div class="resume-panel">'
            '<div class="resume-copy">'
            '<div class="eyebrow">Resume Work</div>'
            '<h2 class="title">Nothing is waiting to resume yet.</h2>'
            '<p class="resume-next">As soon as a real thread has state, artifacts, or worker motion, it will land here as the exact piece of work that needs attention.</p>'
            '<p class="resume-why">The front door stays quiet until there is something real to pick back up.</p>'
            '</div>'
            '<div class="resume-visual"><img src="/steward/assets/resume-quiet-scene.svg" alt="Quiet work scene"><div class="visual-caption"><div class="caption-copy"><strong>Quiet</strong><span>No resume target yet</span></div></div></div>'
            '</div>'
        )

    visual_assets = resume_target.get('visualAssetRefs') or []
    visual = next((asset for asset in visual_assets if asset.get('key') == 'hero'), None)
    next_action = resume_target.get('nextAction') or {}
    return (
        '<div class="resume-panel">'
        '<div class="resume-copy">'
        '<div class="eyebrow">Resume Work</div>'
        f'<div class="status-pill">{escape(_resume_state_label(resume_target))}</div>'
        f'<h2 class="title">{escape(str(resume_target.get("title", "Work waiting")))}</h2>'
        f'<p class="resume-next">{escape(str(next_action.get("text") or "Open the thread and keep it moving."))}</p>'
        f'<p class="resume-why">{escape(str(resume_target.get("whyNow", "This is the clearest thread to resume next.")))}</p>'
        f'{_record_actions("resume", "", resume_target.get("actions", []))}'
        '<div class="resume-facts">'
        f'{_resume_signal("Review", _review_context(resume_target.get("reviewReceipt"), resume_target.get("reviewStatus")))}'
        f'{_resume_signal("Latest artifact", _artifact_context(resume_target.get("latestArtifact")))}'
        f'{_resume_signal("Latest result", _result_context(resume_target.get("latestResult")))}'
        f'{_resume_signal("Worker event", _event_context(resume_target.get("latestWorkerEvent")))}'
        '</div>'
        '</div>'
        '<div class="resume-visual">'
        f'{_resume_image(visual, "Resume state")}'
        '<div class="visual-caption">'
        f'<div class="caption-copy"><strong>{escape(_resume_state_label(resume_target))}</strong><span>{escape(str(resume_target.get("resumeMode", "open")).replace("-", " ").title())}</span></div>'
        f'<div class="caption-copy"><strong>{escape(str(resume_target.get("threadId", "")))}</strong><span>{escape(str(resume_target.get("whyNow", "")))}</span></div>'
        '</div>'
        '</div>'
        '</div>'
    )


def _resume_image(asset: dict | None, alt: str) -> str:
    if not asset or not asset.get('href'):
        return '<img src="/steward/assets/resume-quiet-scene.svg" alt="Quiet work scene">'
    return f'<img src="{escape(str(asset["href"]))}" alt="{escape(alt)}">'


def _resume_state_label(resume_target: dict | None) -> str:
    if not resume_target:
        return 'Quiet'
    state = str(resume_target.get('state', 'quiet'))
    review_status = str(resume_target.get('reviewStatus', 'none'))
    review_verdict = str((resume_target.get('reviewReceipt') or {}).get('verdict') or 'approved')
    if resume_target.get('needsHumanReview'):
        return 'Ready for review'
    if state == 'reviewed':
        if review_verdict == 'revise':
            return 'Changes requested'
        return 'Reviewed'
    if state == 'ready' and review_status == 'reviewed':
        if review_verdict == 'revise':
            return 'Revision ready'
        return 'Ready to continue'
    visual_state = str(resume_target.get('visualState', 'quiet')).replace('-', ' ')
    return visual_state.title()


def _resume_signal(label: str, value: str) -> str:
    return f'<div class="fact"><strong>{escape(label)}</strong><div class="fact-line">{escape(value)}</div></div>'


def _artifact_context(artifact: dict | None) -> str:
    if not artifact:
        return 'No saved artifact yet.'
    return f"{artifact.get('name', 'Artifact')} · {artifact.get('mediaType', 'unknown type')}"


def _review_context(review_receipt: dict | None, review_status: str | None) -> str:
    if review_receipt:
        created_at = review_receipt.get('createdAt') or 'recently'
        verdict = str(review_receipt.get('verdict') or 'approved')
        note = str(review_receipt.get('note') or '').strip()
        prefix = "Changes requested" if verdict == 'revise' else "Reviewed locally"
        if note:
            clipped = note if len(note) <= 90 else note[:89].rstrip() + "…"
            return f"{prefix} · {created_at} · {clipped}"
        return f"{prefix} · {created_at}"
    if review_status == 'pending':
        return 'Still waiting for a local review.'
    return 'No review receipt yet.'


def _result_context(result: dict | None) -> str:
    if not result:
        return 'No worker result yet.'
    summary = result.get('summary') or result.get('status') or 'Recent result.'
    worker_id = result.get('workerId')
    if worker_id:
        return f"{worker_id} · {summary}"
    return str(summary)


def _event_context(event: dict | None) -> str:
    if not event:
        return 'No worker movement yet.'
    detail = event.get('detail') or 'Recent worker event.'
    return f"{event.get('event', 'event')} · {detail}"


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


def _continuity_item(item: dict) -> str:
    title = escape(str(item.get("title", "Project")))
    detail = escape(str(item.get("detail", "Project continuity available.")))
    next_action = item.get("nextAction") or {}
    why_now = item.get("whyNow")
    actions = _record_actions("continuity", "", item.get("actions", []))
    copy = [f'<strong>{title}</strong>', f'<br><span class="muted">{detail}</span>']
    if next_action.get('text'):
        copy.append(f'<br><span class="muted">Next: {escape(str(next_action["text"]))}</span>')
    elif why_now:
        copy.append(f'<br><span class="muted">{escape(str(why_now))}</span>')
    return '<li class="approval-item">' + ''.join(copy) + actions + '</li>'


def _schedule_summary(schedule: dict | None) -> str:
    if not schedule:
        return 'Active hours 08:00-22:00. Heartbeat every 30m.'
    anchors = schedule.get('anchors', {})
    timezone = schedule.get('timezone', 'America/New_York')
    return (
        f"Active hours {schedule.get('activeWindow', '08:00-22:00')} · "
        f"heartbeat every {schedule.get('heartbeatMinutes', 30)}m · "
        f"morning {anchors.get('morning', '08:00')} · "
        f"midday {anchors.get('midday', '13:00')} · "
        f"evening {anchors.get('evening', '21:00')} · "
        f"{timezone}"
    )


def _steward_last_worked_fallback(notification: dict | None, one_next_step: dict) -> dict | None:
    source = notification or one_next_step
    if not source:
        return None

    context = source.get('context')
    kind = source.get('kind') or one_next_step.get('kind')
    if not context and kind:
        context = f"Lane: {str(kind).replace('_', ' ')}"

    actions = list(source.get('actions') or [])
    if not actions:
        actions.append({"label": "Open notifications", "href": "/steward/view/notification_events", "tone": "secondary"})

    return {
        **source,
        "label": source.get('title') or source.get('text') or source.get('label') or "Current steward guidance",
        "detail": source.get('detail') or one_next_step.get('detail') or "Current next step.",
        "context": context,
        "actions": actions,
    }


def _resume_last_worked_fallback(resume_target: dict | None, worker_event: dict | None) -> dict | None:
    if not resume_target:
        if not worker_event:
            return None
        return {
            "label": str(worker_event.get('event') or "Worker").replace('_', ' ').title(),
            "detail": worker_event.get('detail') or "Recent worker movement.",
            "context": "Most recent worker movement.",
            "status": "worker",
            "actions": [{"label": "Open continuity", "href": "/steward/view/continuity", "tone": "secondary"}],
        }

    actions = list(resume_target.get('actions') or [])
    if not actions and resume_target.get('projectUrl'):
        actions.append({"label": "Open thread", "href": resume_target['projectUrl'], "tone": "secondary"})
    if not actions:
        actions.append({"label": "Open continuity", "href": "/steward/view/continuity", "tone": "secondary"})

    latest_artifact = resume_target.get('latestArtifact') or {}
    latest_result = resume_target.get('latestResult') or {}
    latest_event = resume_target.get('latestWorkerEvent') or worker_event or {}
    context = None
    if latest_artifact.get('name'):
        context = f"Latest: {latest_artifact['name']}"
    elif latest_result.get('summary'):
        context = f"Latest result: {latest_result['summary']}"
    elif latest_event.get('detail'):
        context = str(latest_event['detail'])
    elif resume_target.get('whyNow'):
        context = str(resume_target['whyNow'])

    return {
        "label": resume_target.get('title') or "Resume work",
        "detail": (resume_target.get('nextAction') or {}).get('text')
        or resume_target.get('whyNow')
        or "Open the thread and keep it moving.",
        "context": context,
        "status": resume_target.get('resumeMode') or resume_target.get('visualState'),
        "actions": actions[:2],
    }


def _last_worked_item(label: str, item: dict | None) -> str:
    if not item:
        return f'<div class="strip-item"><strong>{escape(label)}</strong><br><span class="muted">Nothing recent.</span></div>'
    title = item.get('label') or item.get('title') or item.get('event') or 'Recent'
    detail = item.get('detail') or item.get('status') or 'Recent activity.'
    context = item.get('context')
    status = item.get('status')
    meta = []
    if context:
        meta.append(f'<span class="muted">{escape(str(context))}</span>')
    if status and str(status) != str(detail):
        meta.append(f'<span class="muted">{escape(str(status).replace("_", " ").replace("-", " ").title())}</span>')
    meta_html = ''.join(f'<br>{line}' for line in meta)
    actions_html = _record_actions('last-worked', str(item.get('ref', '')), item.get('actions', []))
    return (
        f'<div class="strip-item"><strong>{escape(label)}</strong><br>'
        f'{escape(str(title))}<br><span class="muted">{escape(str(detail))}</span>'
        f'{meta_html}{actions_html}</div>'
    )


def _lane_record_item(kind: str, item: dict) -> str:
    title = (
        item.get('title')
        or item.get('label')
        or item.get('name')
        or item.get('roomName')
        or item.get('toolName')
        or item.get('ref')
        or 'Record'
    )
    detail = (
        item.get('detail')
        or item.get('continuity')
        or item.get('recoveryPrompt')
        or item.get('amountText')
        or item.get('location')
        or item.get('state')
        or ''
    )
    ref = str(item.get('ref') or item.get('approvalRef') or item.get('notificationRef') or '')
    actions = item.get('actions', [])
    action_buttons = _record_actions(kind, ref, actions)
    return (
        '<li>'
        f'<strong>{escape(str(title))}</strong><br><span class="muted">{escape(str(detail))}</span>'
        f'{action_buttons}'
        '</li>'
    )


def _record_actions(kind: str, record_ref: str, actions: list[dict]) -> str:
    if not actions:
        return ''
    buttons = []
    for action in actions:
        tone = escape(str(action.get('tone', 'primary')))
        label = escape(str(action.get('label', action.get('action', 'Run'))))
        href = action.get('href')
        post_url = action.get('postUrl')
        record_action = action.get('action')
        if href:
            buttons.append(f'<a class="action-link {tone}" href="{escape(str(href))}">{label}</a>')
            continue
        if post_url:
            buttons.append(f'<button class="{tone}" data-post-url="{escape(str(post_url))}">{label}</button>')
            continue
        approval_ref = action.get('approvalRef')
        decision = action.get('decision')
        if approval_ref and decision:
            buttons.append(
                f'<button class="{tone}" data-approval-ref="{escape(str(approval_ref))}" '
                f'data-decision="{escape(str(decision))}">{label}</button>'
            )
            continue
        if record_ref and record_action:
            buttons.append(
                f'<button class="{tone}" data-kind="{escape(kind)}" '
                f'data-record-ref="{escape(record_ref)}" data-record-action="{escape(str(record_action))}">{label}</button>'
            )
    return f'<div class="record-actions">{"".join(buttons)}</div>'


def _script_json(value: object) -> str:
    return json.dumps(value).replace('</', '<\\/')
