"""Bounded, persistent artifact storage; no inference imports in the MCP process."""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
import uuid
import io
import struct
import wave
from pathlib import Path
from mcp.types import CallToolResult, TextContent, ImageContent, AudioContent, ResourceLink

MAX_BYTES = 64 * 1024 * 1024
INLINE_BYTES = 8 * 1024 * 1024


class ArtifactStore:
    def __init__(self, root):
        self.root = Path(root).expanduser()

    def save(self, data: bytes, mime: str, name="result", metadata=None):
        if len(data) > MAX_BYTES:
            raise ValueError("Artifact exceeds the 64 MiB limit")
        self.root.mkdir(parents=True, exist_ok=True)
        aid = uuid.uuid4().hex
        ext = {"audio/wav": ".wav", "image/png": ".png", "application/json": ".json"}.get(mime) or mimetypes.guess_extension(mime) or ".bin"
        path = self.root / (aid + ext)
        with path.open("xb") as f:
            f.write(data)
        record = {"id": aid, "uri": f"zeroinfer://artifacts/{aid}", "name": name,
                  "mime_type": mime, "bytes": len(data), "created_at": time.time(),
                  "file": path.name, "path": str(path.resolve()), "metadata": metadata or {}}
        if mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            record["width"], record["height"] = struct.unpack(">II", data[16:24])
        if mime == "audio/wav":
            try:
                with wave.open(io.BytesIO(data)) as audio:
                    record.update(sample_rate=audio.getframerate(), channels=audio.getnchannels(),
                                  duration_seconds=audio.getnframes() / audio.getframerate())
            except (wave.Error, EOFError):
                pass
        temp = self.root / (aid + ".pending")
        temp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.root / (aid + ".meta.json"))
        return record

    def get(self, aid):
        if not re.fullmatch(r"[a-f0-9]{32}", aid):
            raise ValueError("Invalid artifact ID")
        record = json.loads((self.root / (aid + ".meta.json")).read_text(encoding="utf-8"))
        path = (self.root / record["file"]).resolve()
        if path.parent != self.root.resolve() or not path.is_file():
            raise ValueError("Artifact is missing or outside the store")
        return record, path

    def list(self, limit=20):
        files = sorted(self.root.glob("*.meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [json.loads(p.read_text(encoding="utf-8")) for p in files[:max(1, min(limit, 100))]]

    def prune(self, older_than_days):
        if older_than_days < 1:
            raise ValueError("Retention must be at least one day")
        count = 0
        for path in self.root.glob("*.meta.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["created_at"] < time.time() - older_than_days * 86400:
                _, data = self.get(record["id"])
                data.unlink()
                path.unlink()
                count += 1
        return {"deleted": count}


def result(summary, metadata=None, media=(), store=None):
    """Emit both machine-readable metadata and native media, with resource fallback."""
    details = dict(metadata or {})
    artifacts, content = [], []
    inline_remaining = INLINE_BYTES
    for raw, mime, name in media:
        artifact = store.save(raw, mime, name, metadata)
        artifacts.append(artifact)
        if len(raw) <= inline_remaining and mime.startswith(("image/", "audio/")):
            cls = ImageContent if mime.startswith("image/") else AudioContent
            content.append(cls(type="image" if cls is ImageContent else "audio", data=base64.b64encode(raw).decode("ascii"), mimeType=mime))
            inline_remaining -= len(raw)
        content.append(ResourceLink(type="resource_link", uri=artifact["uri"], name=name, mimeType=mime, size=len(raw)))
    if artifacts and not details.get("path"):
        details["path"] = artifacts[0]["path"]
    details["artifacts"] = artifacts
    details["summary"] = summary
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(details, ensure_ascii=False)), *content], structuredContent=details)
