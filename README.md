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
cloud-bridge metrics
cloud-bridge health
```

**Caller Contract**
- `/Users/shawnlawyer/cloud-bridge/CALLER_CONTRACT.md`
- Minimal Python caller: `/Users/shawnlawyer/cloud-bridge/examples/minimal_client.py`
- Federated peer spike runbook: `/Users/shawnlawyer/cloud-bridge/FEDERATED_PEER_SPIKE.md`

**License**
MIT
