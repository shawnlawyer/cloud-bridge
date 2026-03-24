# Caller Contract

This document defines the wire contract for callers of the stateless HTTP runtime.

## Global Contract Rules

1. Service is stateless per request.
2. Service mutates no external state.
3. Unsupported or invalid inputs are rejected (fail-closed).
4. No endpoint performs background work.
5. No endpoint escalates permissions.
6. Persistent worker-store operations remain outside the HTTP contract unless explicitly added later.

## Endpoint: `POST /route`

### Request Schema

```json
{
  "type": "object",
  "required": ["envelope", "registry"],
  "properties": {
    "envelope": {
      "type": "object",
      "required": ["gtid", "schema_version", "from_agent", "to_agent", "payload"],
      "properties": {
        "id": {"type": "string", "description": "optional, caller-provided identifier"},
        "gtid": {"type": "string", "pattern": "^cb:\\d+:[^:\\s]+:[^:\\s]+$"},
        "schema_version": {"type": "string", "enum": ["1.0"]},
        "from_agent": {"type": "string"},
        "to_agent": {"type": "string"},
        "payload": {"type": "object"},
        "hop_count": {"type": "integer", "minimum": 0, "default": 0}
      }
    },
    "registry": {
      "type": "object",
      "additionalProperties": {"type": "string"},
      "description": "map of agent_id -> bridge_id"
    }
  }
}
```

### Response Schema

```json
{
  "type": "object",
  "required": ["destination", "metrics"],
  "properties": {
    "destination": {"type": "string"},
    "metrics": {
      "type": "object",
      "additionalProperties": {"type": "integer", "minimum": 0}
    }
  }
}
```

### Curl

```bash
curl -X POST http://localhost:8080/route \
  -H "Content-Type: application/json" \
  -d '{
    "envelope": {
      "gtid": "cb:1:local:test",
      "schema_version": "1.0",
      "from_agent": "a",
      "to_agent": "b",
      "payload": {}
    },
    "registry": {
      "b": "bridge-1"
    }
  }'
```

## Endpoint: `POST /federate`

### Request Schema

```json
{
  "type": "object",
  "required": ["local_id", "remote_id"],
  "properties": {
    "local_id": {"type": "string"},
    "remote_id": {"type": "string"},
    "known_bridges": {
      "type": "array",
      "items": {"type": "string"},
      "default": []
    }
  }
}
```

### Response Schema

```json
{
  "type": "object",
  "required": ["trusted", "state", "metrics"],
  "properties": {
    "trusted": {"type": "boolean"},
    "state": {"type": "string", "enum": ["trusted", "quarantined"]},
    "metrics": {
      "type": "object",
      "additionalProperties": {"type": "integer", "minimum": 0}
    }
  }
}
```

### Curl

```bash
curl -X POST http://localhost:8080/federate \
  -H "Content-Type: application/json" \
  -d '{
    "local_id": "bridge-1",
    "remote_id": "bridge-2",
    "known_bridges": ["bridge-3"]
  }'
```

## Endpoint: `GET /metrics`

### Response Schema

```json
{
  "type": "object",
  "required": ["metrics"],
  "properties": {
    "metrics": {
      "type": "object",
      "additionalProperties": {"type": "integer", "minimum": 0}
    }
  }
}
```

### Curl

```bash
curl http://localhost:8080/metrics
```

## Endpoint: `GET /worker/manifests`

### Response Schema

```json
{
  "type": "object",
  "required": ["manifests", "metrics"],
  "properties": {
    "manifests": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["worker_id", "role", "capabilities", "allowed_task_types", "mode", "summary", "input_keys", "output_keys", "dispatch_policy", "admission_rules"],
        "properties": {
          "worker_id": {"type": "string"},
          "role": {"type": "string"},
          "capabilities": {"type": "array", "items": {"type": "string"}},
          "allowed_task_types": {"type": "array", "items": {"type": "string"}},
          "mode": {"type": "string", "enum": ["analysis-only"]},
          "summary": {"type": "string"},
          "input_keys": {"type": "array", "items": {"type": "string"}},
          "output_keys": {"type": "array", "items": {"type": "string"}},
          "dispatch_policy": {
            "type": "object",
            "required": ["priority", "max_claims_per_cycle"],
            "properties": {
              "priority": {"type": "integer", "minimum": 0},
              "max_claims_per_cycle": {"type": "integer", "minimum": 1}
            }
          },
          "admission_rules": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["task_type", "required_payload_keys", "allow_effects"],
              "properties": {
                "task_type": {"type": "string"},
                "required_payload_keys": {"type": "array", "items": {"type": "string"}},
                "allow_effects": {"type": "boolean"}
              }
            }
          }
        }
      }
    },
    "metrics": {
      "type": "object",
      "additionalProperties": {"type": "integer", "minimum": 0}
    }
  }
}
```

### Curl

```bash
curl http://localhost:8080/worker/manifests
```

## Endpoint: `GET /health`

### Response Schema

```json
{
  "type": "object",
  "required": ["status"],
  "properties": {
    "status": {"type": "string", "enum": ["ok"]}
  }
}
```

### Curl

```bash
curl http://localhost:8080/health
```

## Error Cases

Errors are fail-closed: requests are rejected and no action is taken.

| Endpoint | Condition | Status | Detail |
|---|---|---:|---|
| `POST /route` | missing `envelope` object | `400` | `envelope must be an object` |
| `POST /route` | missing `registry` object | `400` | `registry must be an object` |
| `POST /route` | invalid `schema_version` | `400` | `Unsupported schema version: <value>` |
| `POST /route` | invalid `gtid` format | `400` | `gtid format is invalid` |
| `POST /route` | unknown `to_agent` in registry | `400` | `'Unknown agent'` |
| `POST /route` | `hop_count >= MAX_HOPS` | `400` | `Routing halted: hop cap reached` |
| `POST /federate` | non-string IDs | `400` | `local_id and remote_id must be strings` |
| `POST /federate` | invalid `known_bridges` shape | `400` | `known_bridges must be a list of strings` |

## Explicit Defaults

Defaults are explicit and deterministic:

1. `envelope.hop_count` defaults to `0` when omitted.
2. `federate.known_bridges` defaults to `[]` when omitted.
3. `metrics` counters are in-memory process counters.
