# Worker Spec

## Scope

This document defines Phase 1 of the staff layer: a bounded local worker contract and a deterministic runner.

Phase 1 is intentionally narrow.

- one task per call
- no scheduler
- no background loop
- no hidden state
- no write-to-world permissions

## Task Contract

A worker task is a deterministic instruction to a single named worker.

```json
{
  "task": {
    "task_id": "task-plan-001",
    "thread_id": "kitchen-weekly",
    "worker_id": "planner",
    "task_type": "plan",
    "payload": {
      "items": ["inventory herbs", "review prep list", "order produce"]
    },
    "requires": ["plan"],
    "effects": []
  }
}
```

Fields:

- `task_id`: caller-supplied stable identifier
- `thread_id`: stable workstream identifier
- `worker_id`: registered worker name
- `task_type`: allowed operation for that worker
- `payload`: task input object
- `requires`: required capabilities for this task
- `effects`: requested side effects; must be empty in Phase 1

## Result Contract

A worker result is deterministic and inspectable.

```json
{
  "result": {
    "task_id": "task-plan-001",
    "worker_id": "planner",
    "role": "planner",
    "status": "completed",
    "output": {
      "steps": [
        {"order": 1, "item": "inventory herbs"},
        {"order": 2, "item": "review prep list"},
        {"order": 3, "item": "order produce"}
      ]
    },
    "notes": []
  }
}
```

`status` values:

- `completed`
- `rejected`

Rejections are first-class results. Malformed tasks remain hard errors.

## Default Workers

Phase 1 provides four built-in workers.

### Archivist

- role: `archivist`
- allowed task types: `catalog`, `summarize`
- capabilities: `catalog`, `summarize`, `extract`

### Scribe

- role: `scribe`
- allowed task types: `draft`, `rewrite`
- capabilities: `draft`, `rewrite`, `outline`

### Planner

- role: `planner`
- allowed task types: `plan`, `prioritize`
- capabilities: `plan`, `prioritize`, `sequence`

### Guardian

- role: `guardian`
- allowed task types: `review`, `sanity_check`
- capabilities: `review`, `policy_check`, `risk_check`

## Runner Semantics

The runner:

1. validates the task contract
2. resolves the worker definition
3. rejects non-empty `effects`
4. rejects unsupported `task_type`
5. rejects missing required capabilities
6. executes a deterministic handler
7. returns a structured result

Phase 1 handlers are intentionally simple and deterministic. They prove the contract shape and enforcement path, not autonomous behavior.

## Phase 2 Durable Local Store

Phase 2 adds an inspectable file-backed task store.

Library:

- `/Users/shawnlawyer/cloud-bridge/bridge/workers/store.py`

Stored state:

- `tasks/<task_id>.json`
- `receipts/<receipt_id>.json`
- `events.jsonl`

Store behavior:

1. `enqueue` writes a pending task record
2. `claim` deterministically issues `rcpt:<task_id>:<attempt>`
3. `complete` finalizes the task as `done`
4. `release` requeues until `max_attempts`, then marks `failed`

Task lifecycle values:

- `pending`
- `claimed`
- `done`
- `failed`

Receipt lifecycle values:

- `open`
- `completed`
- `released`

Structured worker rejections are treated as final handled results. They are stored as task status `done` with result status `rejected`.

## Worker Manifests

Phase 2 also adds explicit manifests for the built-in workers.

Library:

- `/Users/shawnlawyer/cloud-bridge/bridge/workers/manifests.py`

The manifests define:

- role summary
- allowed task types
- capabilities
- expected input keys
- expected output keys

## Phase 3 Explicit Orchestration

Phase 3 adds a bounded orchestration layer over the durable store.

Library:

- `/Users/shawnlawyer/cloud-bridge/bridge/workers/orchestrator.py`

Boundaries:

- processes at most one queued task per call
- never spins in a loop
- never schedules itself
- stores every result or release back into the explicit file store
- uses per-manifest dispatch policy instead of raw manifest order

CLI surface:

- `cloud-bridge worker-manifests`
- `cloud-bridge worker-enqueue --store-root <path> < task.json`
- `cloud-bridge worker-store-list --store-root <path>`
- `cloud-bridge worker-process --store-root <path> --worker <worker_id>`
- `cloud-bridge worker-dispatch --store-root <path> --limit <n>`

HTTP surface:

- `GET /worker/manifests`

The HTTP layer remains read-only for manifests. Store mutation and orchestration remain explicit CLI or library operations.

## Phase 4 Cloud Export

Phase 4 adds an explicit cloud transport layer for the worker store.

Library:

- `/Users/shawnlawyer/cloud-bridge/bridge/workers/cloud_transport.py`

Capabilities:

- builds a deterministic export plan for tasks and receipts
- maps pending tasks to per-worker FIFO queue messages
- maps failed tasks to per-worker dead-letter queues
- can sync exported task and receipt records back into the local store
- can replay dead-letter tasks back to `pending`
- can optionally execute that plan through the AWS CLI

CLI surface:

- `cloud-bridge worker-cloud-export --store-root <path> --bucket <bucket> --region <region> --queue-prefix <prefix>`
- `cloud-bridge worker-store-sync --store-root <path> --input <payload.json>`
- `cloud-bridge worker-cloud-replay --store-root <path> --input <payload.json>`
- add `--execute` to apply the plan

## Failure Model

Fail-closed behavior applies at two levels.

Hard errors:

- malformed task object
- unknown worker
- invalid payload type

Structured rejections:

- requested side effects
- unsupported task type for the worker
- required capability missing from the worker

## Interfaces

Library:

- `/Users/shawnlawyer/cloud-bridge/bridge/workers/contracts.py`
- `/Users/shawnlawyer/cloud-bridge/bridge/workers/runner.py`

CLI:

```bash
cloud-bridge worker-run < /Users/shawnlawyer/cloud-bridge/examples/worker_task.json
```

HTTP:

- `POST /worker/run`

## Remaining Boundaries

Not included yet:

- background polling
- autonomous execution

Those belong to later phases.
