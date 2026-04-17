from __future__ import annotations

from pathlib import Path

_ASSET_DIR = Path(__file__).resolve().parent / "assets"

_STATE_ASSET_MAP = {
    "blocked": (
        {
            "kind": "hero",
            "name": "resume-blocked-scene.svg",
            "label": "Blocked work scene",
            "mediaType": "image/svg+xml",
        },
    ),
    "ready": (
        {
            "kind": "hero",
            "name": "resume-ready-scene.svg",
            "label": "Ready work scene",
            "mediaType": "image/svg+xml",
        },
    ),
    "running": (
        {
            "kind": "hero",
            "name": "resume-running-scene.svg",
            "label": "Running work scene",
            "mediaType": "image/svg+xml",
        },
    ),
    "review-needed": (
        {
            "kind": "hero",
            "name": "resume-review-needed-scene.svg",
            "label": "Review needed scene",
            "mediaType": "image/svg+xml",
        },
    ),
    "quiet": (
        {
            "kind": "hero",
            "name": "resume-quiet-scene.svg",
            "label": "Quiet work scene",
            "mediaType": "image/svg+xml",
        },
    ),
}


def asset_refs_for_state(visual_state: str) -> list[dict]:
    state = visual_state if visual_state in _STATE_ASSET_MAP else "quiet"
    refs = []
    for item in _STATE_ASSET_MAP[state]:
        src = f"/steward/assets/{item['name']}"
        refs.append(
            {
                **item,
                "key": item["kind"],
                "src": src,
                "href": src,
            }
        )
    return refs


def resolve_steward_visual_path(asset_name: str) -> Path:
    if not asset_name or "/" in asset_name or "\\" in asset_name:
        raise KeyError("Unknown visual asset")
    path = (_ASSET_DIR / asset_name).resolve()
    if path.parent != _ASSET_DIR.resolve() or not path.exists():
        raise KeyError("Unknown visual asset")
    return path
