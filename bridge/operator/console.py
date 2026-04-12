from __future__ import annotations

from html import escape


def render_operator_console(state: dict) -> str:
    task_counts = state.get("task_counts", {})
    receipt_counts = state.get("receipt_counts", {})
    blocked = state.get("blocked", [])
    recent_events = state.get("recent_events", [])
    expired_receipt_ids = state.get("expired_receipt_ids", [])

    def render_kv_rows(rows: list[tuple[str, object]]) -> str:
        return "".join(
            f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>" for key, value in rows
        )

    def render_count_chips(items: dict) -> str:
        return "".join(
            f'<span class="chip"><strong>{escape(str(key))}</strong> {escape(str(value))}</span>'
            for key, value in sorted(items.items())
        )

    blocked_rows = "".join(
        "<tr>"
        f"<td>{escape(item['task_id'])}</td>"
        f"<td>{escape(item['worker_id'])}</td>"
        f"<td>{escape(item['task_type'])}</td>"
        f"<td>{escape(item['reason'])}</td>"
        "</tr>"
        for item in blocked
    ) or '<tr><td colspan="4">none</td></tr>'

    event_rows = "".join(
        f"<li><code>{escape(event.get('event', 'unknown'))}</code> {escape(_event_summary(event))}</li>"
        for event in recent_events
    ) or "<li>none</li>"

    expired_rows = "".join(f"<li><code>{escape(receipt_id)}</code></li>" for receipt_id in expired_receipt_ids) or "<li>none</li>"

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Cloud Bridge Operator Console</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background: #0f172a; color: #e2e8f0; }}
    h1, h2 {{ margin-bottom: 0.4rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .card {{ background: #111827; border: 1px solid #334155; border-radius: 12px; padding: 16px; }}
    .chip {{ display: inline-block; margin: 4px 6px 0 0; padding: 6px 10px; border-radius: 999px; background: #1e293b; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #334155; vertical-align: top; }}
    code {{ color: #93c5fd; }}
    ul {{ padding-left: 20px; margin: 0; }}
    .muted {{ color: #94a3b8; }}
  </style>
</head>
<body>
  <h1>Cloud Bridge Operator Console</h1>
  <p class=\"muted\">Private hub state on the local store. <a href=\"/projects/research-writing/board\">Open projects</a></p>
  <div class=\"grid\">
    <section class=\"card\">
      <h2>Store Summary</h2>
      <table>{render_kv_rows([
          ("task_count", state.get("task_count", 0)),
          ("receipt_count", state.get("receipt_count", 0)),
          ("artifact_count", state.get("artifact_count", 0)),
          ("event_count", state.get("event_count", 0)),
      ])}</table>
    </section>
    <section class=\"card\">
      <h2>Tasks</h2>
      {render_count_chips(task_counts)}
    </section>
    <section class=\"card\">
      <h2>Receipts</h2>
      {render_count_chips(receipt_counts)}
    </section>
    <section class=\"card\">
      <h2>Expired Leases</h2>
      <ul>{expired_rows}</ul>
    </section>
  </div>
  <div class=\"grid\" style=\"margin-top: 16px;\">
    <section class=\"card\">
      <h2>Blocked Tasks</h2>
      <table>
        <thead><tr><th>task_id</th><th>worker</th><th>type</th><th>reason</th></tr></thead>
        <tbody>{blocked_rows}</tbody>
      </table>
    </section>
    <section class=\"card\">
      <h2>Recent Events</h2>
      <ul>{event_rows}</ul>
    </section>
  </div>
</body>
</html>
"""


def _event_summary(event: dict) -> str:
    parts = []
    for key in ("task_id", "worker_id", "receipt_id", "artifact_id", "owner_id", "reason", "status"):
        if key in event:
            parts.append(f"{key}={event[key]}")
    return " ".join(parts)
