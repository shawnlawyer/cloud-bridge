# Chat Export Ingest

This is the first explicit ingestion path into the worker system.

It is intentionally local and file-based.

## Purpose

The ingester reads a local chat export JSON file and converts each conversation into an archivist task inside the durable worker store.

## Supported Shapes

1. Simplified conversation list:

```json
[
  {
    "id": "conv-1",
    "title": "Session 1",
    "messages": [
      {"role": "user", "text": "hello"},
      {"role": "assistant", "text": "hi"}
    ]
  }
]
```

2. Mapping-based conversation object:

```json
{
  "conversations": [
    {
      "id": "conv-1",
      "title": "Mapped",
      "mapping": {
        "a": {
          "message": {
            "author": {"role": "user"},
            "create_time": 1,
            "content": {"parts": ["first"]}
          }
        }
      }
    }
  ]
}
```

## Output

Each conversation becomes:

- worker: `archivist`
- task type: `summarize`
- task id: `ingest:<conversation_id>`

## CLI

```bash
cloud-bridge ingest-chat-export \
  --input /Users/shawnlawyer/cloud-bridge/examples/chat_export_sample.json \
  --store-root /tmp/cloud-bridge-store
```

The ingester preflights duplicate task IDs before it writes anything.
