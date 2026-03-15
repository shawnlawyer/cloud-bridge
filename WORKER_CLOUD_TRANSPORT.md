# Worker Cloud Transport

This document defines the explicit cloud export layer for the worker store.

## Scope

The transport is explicit and bounded.

- no background sync
- no implicit network activity
- no auto-export on enqueue or completion

## Library

- `/Users/shawnlawyer/cloud-bridge/bridge/workers/cloud_transport.py`

## Model

The transport exports:

- task records to S3 object keys under `tasks/<worker_id>/`
- receipt records to S3 object keys under `receipts/<worker_id>/`
- queue signals for pending tasks to per-worker FIFO queues
- dead-letter signals for failed tasks to per-worker DLQ queues

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

## Dispatch

This layer is intended to pair with bounded dispatch:

```bash
cloud-bridge worker-dispatch --store-root /tmp/cloud-bridge-store --limit 4
```
