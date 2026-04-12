from __future__ import annotations

from html import escape
import json


def render_drop_folder_page(state: dict) -> str:
    summary = state.get("summary", {})
    drop_folders = state.get("drop_folders", [])
    cards = "".join(
        _drop_folder_card(item) for item in drop_folders
    ) or '<article class="card"><h2>No drop folders yet</h2><p class="muted">Register one local folder and use explicit scans so intake stays zero-cost and predictable.</p></article>'
    payload = _script_json(state)
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Cloud Bridge Drop Folders</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; background: #0b1220; color: #e5eefb; }}
    a {{ color: #93c5fd; }}
    textarea, input {{ width: 100%; box-sizing: border-box; background: #0f172a; color: #e5eefb; border: 1px solid #334155; border-radius: 10px; padding: 10px; }}
    button {{ background: #0f766e; color: white; border: 0; border-radius: 999px; padding: 10px 16px; cursor: pointer; margin-right: 10px; margin-bottom: 10px; }}
    button.secondary {{ background: #334155; }}
    .grid {{ display: grid; grid-template-columns: minmax(300px, 420px) 1fr; gap: 18px; align-items: start; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .card {{ background: #111827; border: 1px solid #334155; border-radius: 14px; padding: 16px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }}
    .muted {{ color: #94a3b8; }}
    .chip {{ display: inline-block; margin: 0 8px 8px 0; padding: 6px 10px; background: #1e293b; border-radius: 999px; }}
    .help {{ font-size: 0.95rem; color: #cbd5e1; }}
    code {{ color: #93c5fd; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <p><a href=\"/operator/console\">Operator console</a> · <a href=\"/inbox\">Inbox</a> · <a href=\"/projects/research-writing/board\">Projects</a></p>
  <h1>Cloud Bridge Drop Folders</h1>
  <p class=\"muted\">Explicit local intake only. Nothing here runs as a background daemon; you scan when you want new work to enter the private hub.</p>
  <section class=\"stats\">
    <div class=\"card\"><h2>Registered</h2><p>{escape(str(summary.get("count", 0)))}</p></div>
    <div class=\"card\"><h2>Pending</h2><p>{escape(str(summary.get("pending_count", 0)))}</p></div>
    <div class=\"card\"><h2>Missing</h2><p>{escape(str(summary.get("missing_count", 0)))}</p></div>
  </section>
  <div>
    <button id=\"scan-all\">Scan All</button>
  </div>
  <pre id=\"status\" class=\"muted\"></pre>
  <div class=\"grid\">
    <section class=\"card\">
      <h2>Register Folder</h2>
      <p class=\"help\">Use a folder the app can already see, like <code>/runtime/drop/project-alpha</code> inside the local container.</p>
      <form id=\"register-form\">
        <p><label>Name<br><input name=\"name\" required placeholder=\"research-intake\"></label></p>
        <p><label>Folder path<br><input name=\"folder_path\" required placeholder=\"/runtime/drop/project-alpha\"></label></p>
        <p><label>Title<br><input name=\"title\" required></label></p>
        <p><label>Objective<br><textarea name=\"objective\" rows=\"5\" required></textarea></label></p>
        <p><label>Constraints (one per line)<br><textarea name=\"constraints\" rows=\"4\">local only\nzero cost</textarea></label></p>
        <p><label>Max files<br><input name=\"max_files\" type=\"number\" min=\"1\" value=\"64\"></label></p>
        <p><label>Max bytes per file<br><input name=\"max_bytes\" type=\"number\" min=\"1\" value=\"1000000\"></label></p>
        <p><button type=\"submit\">Register</button></p>
      </form>
    </section>
    <section>
      <div class=\"cards\">{cards}</div>
    </section>
  </div>
  <script>
    window.__CLOUD_BRIDGE_DROP_FOLDERS__ = {escape(payload)};
    const status = document.getElementById('status');
    async function post(path, payload) {{
      status.textContent = 'Working...';
      const response = await fetch(path, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: payload ? JSON.stringify(payload) : undefined,
      }});
      const body = await response.json();
      if (!response.ok) {{
        status.textContent = body.detail || JSON.stringify(body, null, 2);
        return;
      }}
      status.textContent = JSON.stringify(body, null, 2);
      window.location.reload();
    }}
    document.getElementById('scan-all').addEventListener('click', () => post('/drop-folders/scan'));
    document.getElementById('register-form').addEventListener('submit', (event) => {{
      event.preventDefault();
      const data = new FormData(event.target);
      post('/drop-folders/register', {{
        name: (data.get('name') || '').trim(),
        folder_path: (data.get('folder_path') || '').trim(),
        title: (data.get('title') || '').trim(),
        objective: (data.get('objective') || '').trim(),
        constraints: (data.get('constraints') || '').split('\\n').map(v => v.trim()).filter(Boolean),
        max_files: Number(data.get('max_files') || 64),
        max_bytes: Number(data.get('max_bytes') || 1000000),
      }});
    }});
    for (const button of document.querySelectorAll('[data-scan-name]')) {{
      button.addEventListener('click', () => post(`/drop-folders/scan?name=${{encodeURIComponent(button.dataset.scanName)}}`));
    }}
  </script>
</body>
</html>"""


def _drop_folder_card(item: dict) -> str:
    status = "missing" if not item.get("exists", True) else ("pending" if item.get("pending_change_count") else "idle")
    changed = "".join(f"<li>{escape(path)}</li>" for path in item.get("changed_paths", [])) or "<li>none</li>"
    removed = "".join(f"<li>{escape(path)}</li>" for path in item.get("removed_paths", [])) or "<li>none</li>"
    project_link = f'<a href="{escape(item["project_url"])}">Open project</a>' if item.get("project_url") else "-"
    return "".join(
        [
            '<article class="card">',
            f"<h2>{escape(item.get('name', 'drop-folder'))}</h2>",
            f'<p class="muted"><code>{escape(item.get("folder_path", ""))}</code></p>',
            f'<p>{escape(item.get("title", ""))}</p>',
            f'<p><span class="chip">{escape(status)}</span><span class="chip">sources {escape(str(item.get("source_count", 0)))}</span><span class="chip">pending {escape(str(item.get("pending_change_count", 0)))}</span></p>',
            f'<p class="muted">last import {escape(item.get("last_import_at") or "never")} · last scan {escape(item.get("last_scan_at") or "never")}</p>',
            f'<p>{project_link}<br><button class="secondary" data-scan-name="{escape(item.get("name", ""))}">Scan</button></p>',
            "<h3>Changed</h3>",
            f"<ul>{changed}</ul>",
            "<h3>Removed</h3>",
            f"<ul>{removed}</ul>",
            "</article>",
        ]
    )


def _script_json(value: object) -> str:
    return json.dumps(value).replace("</", "<\\/")
