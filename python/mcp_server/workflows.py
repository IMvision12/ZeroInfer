"""Bounded multi-step workflows assembled from the existing inference API."""
from __future__ import annotations

import json
from typing import Any
import math
from mcp.types import CallToolResult
from mcp.server.fastmcp import Context
from mcp_server.artifacts import result


def register(mcp, client, store, read_media, image_url):
    @mcp.tool()
    async def analyze_frames(image_paths: list[str], model: str, question: str = "Describe this frame.", timestamps: list[float] | None = None, ctx: Context = None) -> dict[str, Any]:
        """Analyze up to 16 extracted video frames independently, preserving order and optional times in seconds. This does not decode video files or use a temporal video model."""
        if not 1 <= len(image_paths) <= 16:
            raise ValueError("Provide 1 to 16 frame images")
        if timestamps is not None and (len(timestamps) != len(image_paths) or any(not math.isfinite(t) or t < 0 for t in timestamps)):
            raise ValueError("Provide one nonnegative finite timestamp per frame")
        frames = []
        for i, path in enumerate(image_paths):
            body = await client().post("/v1/tasks/run", {"task": "image-text-to-text", "model": model,
                "inputs": {"dataUrl": image_url(path), "text": question}, "params": {}})
            frames.append({"index": i, "time_seconds": timestamps[i] if timestamps else None, "output": body["output"]})
            if ctx:
                await ctx.report_progress(i + 1, len(image_paths), "Analyzing frames")
        return {"model": model, "frames": frames, "method": "independent frame analysis"}

    @mcp.tool()
    async def speech_to_speech(audio_path: str, text_model: str, speech_model: str, transcription_model: str = "", instruction: str = "Respond helpfully to the user.") -> CallToolResult:
        """Transcribe audio, generate a text response, and synthesize speech. Returns transcript, response and native audio; this is a batch workflow."""
        raw, mime = read_media(audio_path, "audio")
        transcript = await client().post_file("/v1/audio/transcriptions", filename="input.wav", content=raw, mime=mime,
                                             data={"model": transcription_model, "response_format": "json"})
        response = await client().post("/v1/chat/completions", {"model": text_model, "messages": [
            {"role": "system", "content": instruction}, {"role": "user", "content": transcript["text"]}], "max_tokens": 512})
        text = response["choices"][0]["message"]["content"]
        audio = await client().post("/v1/audio/speech", {"model": speech_model, "input": text, "response_format": "wav"})
        return result(text, {"transcript": transcript["text"], "text_model": response["model"], "speech_model": speech_model},
                      [(audio, "audio/wav", "Spoken response")], store())

    @mcp.tool()
    async def index_documents(artifact_ids: list[str], embedding_model: str, chunk_chars: int = 1200, ctx: Context = None) -> dict[str, Any]:
        """Build a local semantic-search index from uploaded UTF-8 text artifacts. PDF/scanned documents must be extracted first. Indexes persist as artifacts."""
        if not 1 <= len(artifact_ids) <= 32 or not 200 <= chunk_chars <= 4000:
            raise ValueError("Use 1–32 documents and chunk_chars between 200 and 4000")
        chunks = []
        for aid in artifact_ids:
            record, path = store().get(aid)
            if not record["mime_type"].startswith("text/"):
                raise ValueError("Only UTF-8 text artifacts can be indexed")
            if path.stat().st_size > 1_000_000:
                raise ValueError("Limit each document to one million bytes")
            text = path.read_text(encoding="utf-8")
            for offset in range(0, len(text), chunk_chars):
                chunks.append({"artifact_id": aid, "name": record["name"], "start_char": offset, "text": text[offset:offset+chunk_chars]})
        if not chunks or len(chunks) > 512:
            raise ValueError("The index must contain 1–512 chunks; split larger collections")
        vectors, actual_model = [], None
        for start in range(0, len(chunks), 32):
            body = await client().post("/v1/embeddings", {"model": embedding_model, "input": [c["text"] for c in chunks[start:start+32]]})
            actual_model = body["model"]
            vectors.extend(d["embedding"] for d in body["data"])
            if ctx:
                await ctx.report_progress(min(start+32, len(chunks)), len(chunks), "Indexing documents")
        artifact = store().save(json.dumps({"model": actual_model, "chunks": chunks, "vectors": vectors}).encode(),
                                "application/json", "Document index", {"kind": "document_index", "model": actual_model})
        return {"index_id": artifact["id"], "chunks": len(chunks), "model": actual_model}

    @mcp.tool()
    async def search_documents(index_id: str, query: str, limit: int = 5) -> dict[str, Any]:
        """Search a local document index, returning source IDs, character offsets, excerpts and cosine scores."""
        if not query.strip() or len(query) > 16000 or not 1 <= limit <= 20:
            raise ValueError("Provide a query of 1–16000 characters and limit of 1–20")
        record, path = store().get(index_id)
        if record.get("metadata", {}).get("kind") != "document_index":
            raise ValueError("Artifact is not a document index")
        index = json.loads(path.read_text(encoding="utf-8"))
        body = await client().post("/v1/embeddings", {"model": index["model"], "input": [query]})
        if body["model"] != index["model"]:
            raise ValueError("Embedding model changed; rebuild the index")
        query_vector = body["data"][0]["embedding"]
        scored = []
        for chunk, vector in zip(index["chunks"], index["vectors"]):
            if len(vector) != len(query_vector):
                raise ValueError("Embedding dimensions changed; rebuild the index")
            norm = math.sqrt(sum(x*x for x in vector) * sum(x*x for x in query_vector))
            score = sum(a*b for a,b in zip(vector, query_vector)) / norm if norm else 0
            scored.append({**chunk, "score": score})
        return {"model": index["model"], "matches": sorted(scored, key=lambda c: c["score"], reverse=True)[:limit]}
