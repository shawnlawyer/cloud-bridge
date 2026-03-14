from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from bridge.workers import FileTaskStore, WorkerTask


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: str
    title: str
    messages: tuple[str, ...]

    def to_task(self) -> WorkerTask:
        return WorkerTask(
            task_id=f"ingest:{self.conversation_id}",
            thread_id=self.conversation_id,
            worker_id="archivist",
            task_type="summarize",
            payload={"title": self.title, "texts": list(self.messages)},
            requires=("summarize",),
            effects=(),
        )


def load_chat_export(path: str | Path) -> tuple[ConversationRecord, ...]:
    export_path = Path(path)
    data = json.loads(export_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("conversations"), list):
        raw_conversations = data["conversations"]
    elif isinstance(data, list):
        raw_conversations = data
    else:
        raise ValueError("chat export must be a list or an object with a conversations list")

    conversations = []
    for raw in raw_conversations:
        conversations.append(_parse_conversation(raw))
    return tuple(conversations)


def ingest_chat_export(path: str | Path, store_root: str | Path, max_attempts: int = 3) -> dict:
    conversations = load_chat_export(path)
    store = FileTaskStore(store_root)
    tasks = [conversation.to_task() for conversation in conversations]

    existing = {record.task.task_id for record in store.list_tasks()}
    duplicates = sorted(task.task_id for task in tasks if task.task_id in existing)
    if duplicates:
        raise ValueError(f"tasks already exist: {', '.join(duplicates)}")

    enqueued = []
    for task in tasks:
        store.enqueue(task, max_attempts=max_attempts)
        enqueued.append(task.task_id)

    return {
        "input_path": str(Path(path)),
        "conversation_count": len(conversations),
        "task_count": len(enqueued),
        "task_ids": enqueued,
    }


def _parse_conversation(raw: object) -> ConversationRecord:
    if not isinstance(raw, dict):
        raise ValueError("conversation entry must be an object")

    conversation_id = raw.get("id") or raw.get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id:
        raise ValueError("conversation id is required")

    title = raw.get("title", conversation_id)
    if not isinstance(title, str):
        raise ValueError("conversation title must be a string")

    if isinstance(raw.get("mapping"), dict):
        messages = _messages_from_mapping(raw["mapping"])
    else:
        messages = _messages_from_list(raw.get("messages", []))

    if not messages:
        raise ValueError("conversation messages are required")

    return ConversationRecord(
        conversation_id=conversation_id,
        title=title,
        messages=tuple(messages),
    )


def _messages_from_mapping(mapping: dict) -> list[str]:
    extracted = []
    for node_id, node in mapping.items():
        if not isinstance(node, dict):
            continue
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content", {})
        if not isinstance(content, dict):
            continue
        parts = content.get("parts", [])
        if not isinstance(parts, list):
            continue
        text = " ".join(part for part in parts if isinstance(part, str)).strip()
        if not text:
            continue
        author = message.get("author", {})
        role = author.get("role", "unknown") if isinstance(author, dict) else "unknown"
        create_time = message.get("create_time")
        if isinstance(create_time, (int, float)):
            sort_key = (float(create_time), str(node_id))
        else:
            sort_key = (float("inf"), str(node_id))
        extracted.append((sort_key, f"{role}: {text}"))

    extracted.sort(key=lambda item: item[0])
    return [text for _, text in extracted]


def _messages_from_list(messages: object) -> list[str]:
    if not isinstance(messages, list):
        raise ValueError("conversation messages must be a list")

    normalized = []
    for item in messages:
        if isinstance(item, str):
            normalized.append(item)
            continue
        if not isinstance(item, dict):
            raise ValueError("conversation message entries must be strings or objects")

        role = item.get("role")
        prefix = f"{role}: " if isinstance(role, str) and role else ""

        if isinstance(item.get("text"), str):
            normalized.append(prefix + item["text"])
            continue
        if isinstance(item.get("content"), str):
            normalized.append(prefix + item["content"])
            continue
        parts = item.get("parts", [])
        if isinstance(parts, list) and all(isinstance(part, str) for part in parts):
            normalized.append(prefix + " ".join(parts))
            continue
        raise ValueError("conversation message object must contain text, content, or parts")

    return normalized
