"""Pushes finished API results to the desktop's output viewer window.

The app's own workspaces render their results inline, so this fires only for
inference driven from *outside* the app: the HTTP API, and through it the MCP
server. Those callers get JSON back and the human sitting in front of the
machine gets nothing to look at - an agent runs a detection and the boxes exist
only as numbers in someone else's context window. This closes that gap. The
engine hands the finished artifact to Electron over the stdio event channel it
already has, and Electron pops a window that can actually show it.

It is also the answer to a problem we could not solve anywhere else: an MCP
client renders the image only if it feels like it, and Claude Desktop's chat
does not. Rendering in our own window means the result is visible no matter
which client asked for it, or how that client treats image content.

Kinds come straight from output_kinds.py. Media is described by its MIME type
rather than by task, so an adapter that starts emitting video needs no change
here - `data:video/mp4;base64,...` already arrives tagged as a video.
"""
from __future__ import annotations

import time
import uuid

from services.events import HUB

EVENT = "viewer:output"

_PLAYABLE = ("image", "audio", "video")


def _mime(data_url) -> str:
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        return ""
    return data_url.split(";", 1)[0][len("data:"):]


def _media(src) -> dict | None:
    """A data URL -> a renderable item, typed by its own MIME."""
    mime = _mime(src)
    if not mime:
        return None
    family = mime.split("/", 1)[0]
    return {
        "type": family if family in _PLAYABLE else "file",
        "mime": mime,
        "src": src,
    }


def items_for(out: dict) -> list[dict]:
    """Flatten one output_kinds dict into things a window can render."""
    out = out or {}
    kind = out.get("kind")
    items: list[dict] = []

    if kind == "multimodal":
        return [item for output in out.get("items", []) for item in items_for(output)]

    if kind in ("image", "audio"):
        items.append(_media(out.get("dataUrl")))
    elif kind == "masks":
        # `annotated` is the overlay composited onto the original; the bare
        # overlay is transparent RGBA and reads as noise on its own.
        items.append(_media(out.get("annotated") or out.get("overlay")))
        if out.get("legend"):
            items.append({"type": "legend", "legend": out["legend"]})
    elif kind == "boxes":
        # Adapters draw the boxes whether or not the caller asked for the PNG,
        # so there is always a picture here even when the HTTP response is
        # nothing but coordinates. A detector that found nothing still gets a
        # window - the annotated image is the answer to "did it see anything?".
        items.append(_media(out.get("annotated")))
        if out.get("boxes"):
            items.append({"type": "boxes", "boxes": out["boxes"]})
    elif kind == "text":
        # An empty transcript is not worth a window.
        if (out.get("text") or "").strip():
            items.append({"type": "text", "text": out["text"]})
    elif kind == "labels":
        if out.get("labels"):
            items.append({"type": "labels", "labels": out["labels"]})
    elif kind == "vector":
        items.append({"type": "vector", "dim": out.get("dim"),
                      "sample": out.get("sample") or []})
    elif out.get("dataUrl"):
        # An adapter emitting a kind this function has never heard of still has
        # its media shown, as long as it carries a data URL.
        items.append(_media(out["dataUrl"]))

    return [i for i in items if i]


def publish(model: str, task, out: dict) -> None:
    """Announce one finished result. Never raises: a viewer that is not
    listening must not fail the API call that produced the result."""
    try:
        items = items_for(out)
        if not items:
            return
        HUB.publish(EVENT, {
            "id": uuid.uuid4().hex,
            "model": model,
            "task": task or (out or {}).get("kind") or "",
            "createdAt": int(time.time() * 1000),
            "items": items,
        })
    except Exception:
        pass
