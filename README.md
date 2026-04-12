# Cloud Bridge

Cloud Bridge is a deterministic, federated coordination substrate for multi-agent systems.

It is not autonomous. It does not act on the world. It produces analysis, coordination, and intent only.

**System Identity**
- Instrument (always)
- Substrate (enabled)
- Operator (explicitly disabled)

**Permissions**
- P1 / P2 / P3 only
- No write-to-world operations
- No schedulers or background loops

**Design Guarantees**
- Deterministic routing
- Bounded message propagation
- Fail-closed defaults
- Schema version negotiation
- Federation without authority transfer

**Non-Negotiable Constraints**
- No cron jobs
- No background threads
- No hidden state
- No side effects
- All state must be inspectable
- All failures must halt, not retry infinitely

**Core Concepts**
- Envelope: Immutable, validated message container
- Federation: Bridge-to-bridge coordination without command authority
- Consensus: Recommendation only, no execution
- Connectors: Read-only structure only

**Installation (optional)**
```bash
pip install -e .
```

**Run Examples**
```bash
python examples/single_bridge_demo.py
python examples/federation_demo.py
```

**Run Tests**
```bash
python -m unittest
```

**Runtime**
- `HTTP`: stateless request/response service
- `CLI`: local deterministic wrapper
- `Private hub default`: local filesystem first, cloud disabled unless explicitly enabled
- `No background daemon`: no scheduler, no hidden loop lifecycle
- `Staff Phase 1`: bounded local worker contract and runner
- `Staff Phase 2`: durable local task store and explicit worker manifests
- `Staff Phase 3`: bounded orchestration and first ingestion path
- `Staff Phase 4`: explicit cloud export plan for the worker store
- `Staff Phase 5`: bounded cloud fetch/import, lease reclaim, and manifest admission rules
- `Staff Phase 6`: zero-cost local maintenance and cloud opt-in guardrails
- `Staff Phase 7`: private LAN operator console, local artifact storage, and bounded research/writing workflow
- `Staff Phase 8`: browser-based project intake, workflow dashboards, artifact preview, and folder import
- `Persistent store`: explicit CLI/library component only; not enabled implicitly by HTTP

**HTTP Service**
Install API extras:
```bash
pip install -e ".[api]"
```

Default local-only bind:
```bash
uvicorn bridge.api.app:app --host 127.0.0.1 --port 8080
```

Private LAN bind, only if you intentionally want other devices on your local network to reach it:
```bash
uvicorn bridge.api.app:app --host 0.0.0.0 --port 8080
```

Run:
Endpoints:
- `POST /route`
- `POST /federate`
- `POST /worker/run`
- `GET /worker/manifests`
- `GET /operator/state`
- `GET /operator/console`
- `GET /inbox/state`
- `GET /inbox`
- `POST /inbox/dispatch`
- `POST /inbox/reclaim`
- `POST /inbox/maintain`
- `GET /projects/research-writing`
- `GET /projects/research-writing/board`
- `POST /projects/research-writing/bootstrap`
- `POST /projects/research-writing/import-folder`
- `GET /projects/research-writing/{thread_id}`
- `GET /projects/research-writing/{thread_id}/view`
- `POST /projects/research-writing/{thread_id}/dispatch`
- `POST /projects/research-writing/{thread_id}/assemble`
- `GET /artifacts`
- `GET /artifacts/{artifact_id}`
- `GET /metrics`
- `GET /health`

Operator console with an explicit local store root:
```bash
CLOUD_BRIDGE_STORE_ROOT=/tmp/cloud-bridge-store \
uvicorn bridge.api.app:app --host 127.0.0.1 --port 8080
```

Then open:
- `http://127.0.0.1:8080/operator/console`
- `http://<LAN_IP>:8080/operator/console`
- `http://<LAN_IP>:8080/inbox`
- `http://<LAN_IP>:8080/projects/research-writing/board`

**Docker**
Build:
```bash
docker build -t cloud-bridge:0.1.2 .
```

Run:
```bash
docker run --rm \
  -e CLOUD_BRIDGE_HOST=0.0.0.0 \
  -p 127.0.0.1:8080:8080 \
  cloud-bridge:0.1.2
```

Health check:
```bash
curl http://localhost:8080/health
```

Private LAN Docker example, only if you intentionally want access from your local network:
```bash
docker run --rm \
  -e CLOUD_BRIDGE_HOST=0.0.0.0 \
  -p <LAN_IP>:8080:8080 \
  cloud-bridge:0.1.2
```

Example `POST /route` body:
```json
{
  "envelope": {
    "gtid": "cb:1:bridge-1:thread-1",
    "schema_version": "1.0",
    "from_agent": "agent-a",
    "to_agent": "agent-b",
    "payload": {"task": "summarize"}
  },
  "registry": {
    "agent-b": "bridge-2"
  }
}
```

Route test:
```bash
curl -X POST http://localhost:8080/route \
  -H "Content-Type: application/json" \
  -d '{"envelope":{"gtid":"cb:1:local:test","schema_version":"1.0","from_agent":"a","to_agent":"b","payload":{}},"registry":{"b":"bridge-1"}}'
```

Example `POST /federate` body:
```json
{
  "local_id": "bridge-1",
  "remote_id": "bridge-2",
  "known_bridges": ["bridge-3"]
}
```

**CLI**
```bash
cloud-bridge route < input.json
cloud-bridge federate < input.json
cloud-bridge worker-run < /Users/shawnlawyer/cloud-bridge/examples/worker_task.json
cloud-bridge worker-manifests
cloud-bridge worker-enqueue --store-root /tmp/cloud-bridge-store < /Users/shawnlawyer/cloud-bridge/examples/worker_task.json
cloud-bridge worker-store-list --store-root /tmp/cloud-bridge-store
cloud-bridge worker-store-status --store-root /tmp/cloud-bridge-store --event-limit 20
cloud-bridge worker-inbox --store-root /tmp/cloud-bridge-store --task-limit 40
cloud-bridge worker-store-maintain --store-root /tmp/cloud-bridge-store --keep-done 100 --keep-failed 50 --event-keep 1000
cloud-bridge worker-artifact-add --store-root /tmp/cloud-bridge-store --owner-id workflow:notes --input ./notes.md
printf '# quick note\n' | cloud-bridge worker-artifact-add --store-root /tmp/cloud-bridge-store --owner-id workflow:notes --input - --name quick-note.md
cloud-bridge worker-artifact-list --store-root /tmp/cloud-bridge-store --owner-id workflow:notes
cloud-bridge worker-store-sync --store-root /tmp/cloud-bridge-store --input export.json
cloud-bridge worker-process --store-root /tmp/cloud-bridge-store --worker planner
cloud-bridge worker-dispatch --store-root /tmp/cloud-bridge-store --limit 4
cloud-bridge worker-reclaim --store-root /tmp/cloud-bridge-store
cloud-bridge worker-cloud-replay --store-root /tmp/cloud-bridge-store --input export.json
cloud-bridge research-writing-bootstrap --store-root /tmp/cloud-bridge-store --title "Local Hub Primer" --objective "Explain the private hub" --source ./notes/source.md --constraint "local only" --constraint "zero cost"
cloud-bridge research-writing-import-folder --store-root /tmp/cloud-bridge-store --folder ./notes/project-alpha --title "Project Alpha" --objective "Turn the folder into a working draft" --constraint "local only"
cloud-bridge research-writing-list --store-root /tmp/cloud-bridge-store
cloud-bridge research-writing-status --store-root /tmp/cloud-bridge-store --thread-id research:local-hub-primer
cloud-bridge worker-dispatch --store-root /tmp/cloud-bridge-store --thread-id research:local-hub-primer --limit 4
cloud-bridge research-writing-assemble --store-root /tmp/cloud-bridge-store --thread-id research:local-hub-primer
cloud-bridge ingest-chat-export --input /Users/shawnlawyer/cloud-bridge/examples/chat_export_sample.json --store-root /tmp/cloud-bridge-store
cloud-bridge metrics
cloud-bridge health
```

**Local Artifact Store**
- Artifacts live inside the worker store under `artifacts/files` and `artifacts/meta`.
- Each artifact records owner, media type, size, hash, and on-disk path.
- The artifact store stays zero-cost and local until you explicitly opt into cloud commands later.

**Bounded Research/Writing Workflow**
- `research-writing-bootstrap` imports local sources, writes a workflow packet, and enqueues four bounded tasks:
  - `guardian` for Steward constraints/risk review
  - `archivist` for source digest
  - `planner` for ordered steps
  - `scribe` for a first-pass draft
- `research-writing-import-folder` walks a local folder, imports supported text-like files, and turns the whole folder into one bounded project.
- `research-writing-list` gives you a compact project index you can use from scripts or the browser board.
- `worker-dispatch --limit 4` can process the whole workflow in one bounded cycle.
- `worker-dispatch --thread-id ... --limit 4` scopes dispatch to one project instead of the whole store.
- `research-writing-assemble` writes a markdown artifact that combines the completed outputs into a single working draft.

**Browser-First Local Use**
- `/inbox` is the work queue page: what is ready, blocked, failed, or stuck right now.
- The inbox can run a bounded global dispatch, reclaim expired leases, or maintain the store from the browser.
- The inbox can also dispatch one thread at a time so one project does not trample another.
- `/projects/research-writing/board` is a lightweight intake screen for new projects.
- The board can start a project from newline-separated source paths or a server-local folder path.
- Each project page can run a bounded dispatch and assemble a fresh draft from the browser.
- `/artifacts/{artifact_id}` lets you preview/download local outputs without any paid service.

**Zero-Cost Defaults**
- Local filesystem is the default runtime.
- Local maintenance commands keep the worker store bounded without paying for any service.
- Cloud access is disabled by default.
- To enable live AWS commands later, you must explicitly set `CLOUD_BRIDGE_ENABLE_CLOUD=1`.
- Default HTTP examples bind locally first; LAN access is explicit.

**Cloud Commands Are Opt-In**
These commands stay available for later, but they are blocked unless `CLOUD_BRIDGE_ENABLE_CLOUD=1` is set:

```bash
cloud-bridge worker-cloud-export --store-root /tmp/cloud-bridge-store --bucket cloudbridge-bucket --region us-east-2 --queue-prefix cloudbridge --execute
cloud-bridge worker-cloud-fetch --bucket cloudbridge-bucket --region us-east-2 --queue-prefix cloudbridge --workers planner --queue-message-limit 2
cloud-bridge worker-cloud-import --store-root /tmp/cloud-bridge-store --bucket cloudbridge-bucket --region us-east-2 --queue-prefix cloudbridge --workers planner --queue-message-limit 2 --replay-dead-letters
```

**Caller Contract**
- `/Users/shawnlawyer/cloud-bridge/CALLER_CONTRACT.md`
- Minimal Python caller: `/Users/shawnlawyer/cloud-bridge/examples/minimal_client.py`
- Federated peer spike runbook: `/Users/shawnlawyer/cloud-bridge/FEDERATED_PEER_SPIKE.md`
- Staff gap analysis: `/Users/shawnlawyer/cloud-bridge/STAFF_GAP_ANALYSIS.md`
- Worker spec: `/Users/shawnlawyer/cloud-bridge/WORKER_SPEC.md`
- Chat export ingest: `/Users/shawnlawyer/cloud-bridge/CHAT_EXPORT_INGEST.md`
- Worker cloud transport: `/Users/shawnlawyer/cloud-bridge/WORKER_CLOUD_TRANSPORT.md`
- Worker manifests: `/Users/shawnlawyer/cloud-bridge/bridge/workers/manifests.py`
- Durable task store: `/Users/shawnlawyer/cloud-bridge/bridge/workers/store.py`
- Worker orchestration: `/Users/shawnlawyer/cloud-bridge/bridge/workers/orchestrator.py`

**License**
MIT
