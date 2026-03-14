# Staff Gap Analysis

## Original Vision

The original CloudBridge concept was a multi-role coordination system built on top of a shared transport. The durable parts of that vision were:

- structured message envelopes
- append-only logs and inspectable state
- transport progression from local filesystem to cloud messaging
- bounded worker roles such as `Archivist`, `Scribe`, `Planner`, and `Guardian`
- human-operated infrastructure with machine-handled digital coordination

The unstable part of the original vision was the autonomy language. The transcript repeatedly described self-directed behavior, but it did not define a safe execution model for that behavior.

## Current Implementation

The repository currently provides the substrate, not the staff layer.

- Deterministic message validation lives in `/Users/shawnlawyer/cloud-bridge/bridge/core/envelope.py`.
- Deterministic routing lives in `/Users/shawnlawyer/cloud-bridge/bridge/core/routing.py`.
- Federation validation lives in `/Users/shawnlawyer/cloud-bridge/bridge/federation/handshake.py`.
- Stateless runtime wrappers live in `/Users/shawnlawyer/cloud-bridge/bridge/api/app.py` and `/Users/shawnlawyer/cloud-bridge/bridge/cli.py`.
- Constraint and contract documentation lives in `/Users/shawnlawyer/cloud-bridge/INVARIANTS.md`, `/Users/shawnlawyer/cloud-bridge/CALLER_CONTRACT.md`, and `/Users/shawnlawyer/cloud-bridge/FEDERATED_PEER_SPIKE.md`.

This codebase is explicitly:

- stateless per request
- fail-closed
- deterministic
- non-autonomous

## Missing Pieces

The current repository does not yet implement the system implied by the original transcript.

### 1. Worker Contract

Missing:

- a formal task contract for role workers
- a formal result contract for role workers
- capability gating and allowed task-type enforcement
- explicit stop conditions per worker

### 2. Persistent Coordination State

Missing:

- durable task storage
- durable artifact storage
- durable thread history
- persisted receipts and retries

### 3. Cloud Transport

Missing:

- an actual S3/SQS transport implementation in the repository
- queue provisioning and IAM bootstrap code
- DLQ handling and recovery logic

### 4. Orchestration

Missing:

- task claiming
- leases or receipts
- deterministic dispatch across multiple workers
- merge and escalation rules between workers

### 5. Ingestion

Missing:

- adapters for conversation exports
- adapters for shared links
- adapters for files, email, or other source systems

### 6. Staff Layer

Missing:

- concrete manifests for `Archivist`, `Scribe`, `Planner`, and `Guardian`
- bounded outputs for each role
- policy rules for cross-role handoff

## Safe Build Order

The correct build order is:

1. Define the worker task/result contract.
2. Implement a local bounded runner that processes one task per call.
3. Add durable local task state.
4. Add worker manifests for the four roles.
5. Add cloud transport and receipts.
6. Add one real ingestion path.

## Phase 1 Outcome

Phase 1 should not attempt autonomy. It should only provide:

- a bounded worker contract
- deterministic local execution
- explicit rejection of side effects
- inspectable results

That is the first honest step from substrate to staff.
