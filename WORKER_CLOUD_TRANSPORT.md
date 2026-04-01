# Worker Cloud Transport

This document defines the explicit cloud export layer for the worker store.

## Scope

The transport is explicit and bounded.

- no background sync
- no implicit network activity
- no auto-export on enqueue or completion
- disabled by default at the CLI layer unless `CLOUD_BRIDGE_ENABLE_CLOUD=1`

## Library

- `/Users/shawnlawyer/cloud-bridge/bridge/workers/cloud_transport.py`

## Model

The transport exports:

- task records to S3 object keys under `tasks/<worker_id>/`
- receipt records to S3 object keys under `receipts/<worker_id>/`
- queue signals for pending tasks to per-worker FIFO queues
- dead-letter signals for failed tasks to per-worker DLQ queues

The transport also supports bounded live fetch/import:

- fetch current task and receipt objects from S3
- fetch queue and DLQ messages from SQS
- sync fetched records into the local store
- replay DLQ tasks back to `pending`
- optionally delete fetched queue messages after a successful import

## CLI

```bash
cloud-bridge worker-cloud-export \
  --store-root /tmp/cloud-bridge-store \
  --bucket cloudbridge-bucket \
  --region us-east-2 \
  --queue-prefix cloudbridge
```

Add `--execute` to actually call the AWS CLI.

Without `--execute`, the command returns the export plan only.

## Store Sync

Import task and receipt records from a saved export payload:

```bash
cloud-bridge worker-store-sync \
  --store-root /tmp/cloud-bridge-store \
  --input export.json
```

## Dead-Letter Replay

Replay failed tasks from a saved export payload:

```bash
cloud-bridge worker-cloud-replay \
  --store-root /tmp/cloud-bridge-store \
  --input export.json
```

## Live Fetch

Fetch a bounded payload directly from AWS without mutating the local store:

```bash
cloud-bridge worker-cloud-fetch \
  --bucket cloudbridge-bucket \
  --region us-east-2 \
  --queue-prefix cloudbridge \
  --workers planner \
  --queue-message-limit 2
```

This is the cheap path by default:

- `task_object_limit=0`
- `receipt_object_limit=0`
- `queue_message_limit=2`

That means queue reads are bounded and S3 listing is skipped unless you opt in.

## Live Import

Fetch directly from AWS and sync into the local worker store:

```bash
cloud-bridge worker-cloud-import \
  --store-root /tmp/cloud-bridge-store \
  --bucket cloudbridge-bucket \
  --region us-east-2 \
  --queue-prefix cloudbridge \
  --workers planner \
  --queue-message-limit 2 \
  --replay-dead-letters
```

Optional flags:

- `--task-object-limit <n>`: bounded S3 task-object scan
- `--receipt-object-limit <n>`: bounded S3 receipt-object scan
- `--exclude-dlq`: skip DLQ reads
- `--force`: overwrite weaker local task/receipt state
- `--delete-fetched`: delete fetched SQS messages after a successful import

## Dispatch

This layer is intended to pair with bounded dispatch:

```bash
cloud-bridge worker-dispatch --store-root /tmp/cloud-bridge-store --limit 4
```

Dispatch now also:

- reclaims expired leases before it starts work
- filters pending tasks through manifest admission rules before claiming them
