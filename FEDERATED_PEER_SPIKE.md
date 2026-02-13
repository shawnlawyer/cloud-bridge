# Federated Peer Integration Spike (Bounded)

This spike proves two independent containers can handshake, route once, terminate cleanly, and remain stateless.

## Scope Guarantees

1. No background process orchestration is introduced.
2. No auto-discovery is introduced.
3. No new permissions are introduced.
4. Calls are manual and request-scoped.
5. Fail-closed behavior is explicit.

## Precondition

Build image:

```bash
docker build -t cloud-bridge:0.1.2 .
```

Create network:

```bash
docker network create cb-net
```

## Start Two Peers

Terminal A:

```bash
docker run --rm --name cb-a --network cb-net -e BRIDGE_ID=bridge-a -p 18080:8080 cloud-bridge:0.1.2
```

Terminal B:

```bash
docker run --rm --name cb-b --network cb-net -e BRIDGE_ID=bridge-b -p 28080:8080 cloud-bridge:0.1.2
```

Notes:

1. Containers are independent processes.
2. `BRIDGE_ID` is an operator label for this spike. Current API uses request payload IDs (`local_id`, `remote_id`) for handshake decisions.

## Sequence: Prove Federation + Routing

### 1) Health checks

```bash
curl http://localhost:18080/health
curl http://localhost:28080/health
```

Expected:

```json
{"status":"ok"}
```

### 2) Manual bootstrap handshake (`cb-a` -> `cb-b`)

```bash
curl -X POST http://localhost:18080/federate \
  -H "Content-Type: application/json" \
  -d '{"local_id":"bridge-a","remote_id":"bridge-b","known_bridges":[]}'
```

Expected:

```json
{"trusted":true,"state":"trusted","metrics":{"federate":1}}
```

### 3) Manual bootstrap handshake (`cb-b` -> `cb-a`)

```bash
curl -X POST http://localhost:28080/federate \
  -H "Content-Type: application/json" \
  -d '{"local_id":"bridge-b","remote_id":"bridge-a","known_bridges":[]}'
```

Expected:

```json
{"trusted":true,"state":"trusted","metrics":{"federate":1}}
```

### 4) Route one message from `cb-a` to `bridge-b`

```bash
curl -X POST http://localhost:18080/route \
  -H "Content-Type: application/json" \
  -d '{
    "envelope":{
      "gtid":"cb:1:bridge-a:msg-1",
      "schema_version":"1.0",
      "from_agent":"agent-a",
      "to_agent":"peer-b",
      "payload":{"msg":"hello"}
    },
    "registry":{"peer-b":"bridge-b"}
  }'
```

Expected:

```json
{"destination":"bridge-b","metrics":{"federate":1,"route":1}}
```

Interpretation:

1. Schema negotiation outcome is deterministic: `"1.0"` is accepted.
2. Routing resolves exactly once and returns.
3. No loop path is entered by default.

### 5) Confirm metrics on both peers

```bash
curl http://localhost:18080/metrics
curl http://localhost:28080/metrics
```

Expected:

Peer `cb-a`:

```json
{"metrics":{"federate":1,"route":1}}
```

Peer `cb-b`:

```json
{"metrics":{"federate":1}}
```

## Fail-Closed Cases

### A) Schema mismatch (negotiation reject)

```bash
curl -X POST http://localhost:18080/route \
  -H "Content-Type: application/json" \
  -d '{
    "envelope":{
      "gtid":"cb:1:bridge-a:msg-bad-schema",
      "schema_version":"9.9",
      "from_agent":"agent-a",
      "to_agent":"peer-b",
      "payload":{}
    },
    "registry":{"peer-b":"bridge-b"}
  }'
```

Expected:

```json
{"detail":"Unsupported schema version: 9.9"}
```

### B) Hop cap reject (termination guard)

```bash
curl -X POST http://localhost:18080/route \
  -H "Content-Type: application/json" \
  -d '{
    "envelope":{
      "gtid":"cb:1:bridge-a:msg-hop-cap",
      "schema_version":"1.0",
      "from_agent":"agent-a",
      "to_agent":"peer-b",
      "payload":{},
      "hop_count":8
    },
    "registry":{"peer-b":"bridge-b"}
  }'
```

Expected:

```json
{"detail":"Routing halted: hop cap reached"}
```

These two failures are hard rejections (fail-closed), not recovery flows.

## Clean Termination

```bash
docker stop cb-a cb-b
docker network rm cb-net
```

Result:

1. Both peers terminate immediately.
2. No persisted runtime state remains.
