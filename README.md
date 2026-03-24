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
- `No background daemon`: no scheduler, no hidden loop lifecycle
- `Staff Phase 1`: bounded local worker contract and runner
- `Staff Phase 2`: durable local task store and explicit worker manifests
- `Staff Phase 3`: bounded orchestration and first ingestion path
- `Staff Phase 4`: explicit cloud export plan for the worker store
- `Staff Phase 5`: bounded cloud fetch/import, lease reclaim, and manifest admission rules
- `Persistent store`: explicit CLI/library component only; not enabled implicitly by HTTP

**HTTP Service**
Install API extras:
```bash
pip install -e ".[api]"
```

Run:
```bash
uvicorn bridge.api.app:app --host 0.0.0.0 --port 8080
```

Endpoints:
- `POST /route`
- `POST /federate`
- `POST /worker/run`
- `GET /worker/manifests`
- `GET /metrics`
- `GET /health`

**Docker**
Build:
```bash
docker build -t cloud-bridge:0.1.2 .
```

Run:
```bash
docker run --rm -p 8080:8080 cloud-bridge:0.1.2
```

Health check:
```bash
curl http://localhost:8080/health
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
cloud-bridge worker-store-sync --store-root /tmp/cloud-bridge-store --input export.json
cloud-bridge worker-process --store-root /tmp/cloud-bridge-store --worker planner
cloud-bridge worker-dispatch --store-root /tmp/cloud-bridge-store --limit 4
cloud-bridge worker-reclaim --store-root /tmp/cloud-bridge-store
cloud-bridge worker-cloud-export --store-root /tmp/cloud-bridge-store --bucket cloudbridge-bucket --region us-east-2 --queue-prefix cloudbridge
cloud-bridge worker-cloud-fetch --bucket cloudbridge-bucket --region us-east-2 --queue-prefix cloudbridge --workers planner --queue-message-limit 2
cloud-bridge worker-cloud-import --store-root /tmp/cloud-bridge-store --bucket cloudbridge-bucket --region us-east-2 --queue-prefix cloudbridge --workers planner --queue-message-limit 2 --replay-dead-letters
cloud-bridge worker-cloud-replay --store-root /tmp/cloud-bridge-store --input export.json
cloud-bridge ingest-chat-export --input /Users/shawnlawyer/cloud-bridge/examples/chat_export_sample.json --store-root /tmp/cloud-bridge-store
cloud-bridge metrics
cloud-bridge health
```

**Cloud Cost Guardrails**
- No new managed services were added beyond the existing optional `S3` + `SQS` path.
- Live cloud fetch/import is explicit CLI work only; there is no background polling.
- The live fetch/import commands default to `queue_message_limit=2` and `task_object_limit=0` / `receipt_object_limit=0`, so they do not scan S3 unless you ask them to.

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
