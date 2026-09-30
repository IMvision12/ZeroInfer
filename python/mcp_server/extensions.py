"""Additional tools over the shared task API and artifact store."""
from __future__ import annotations

import base64
import json
from typing import Any
from mcp.types import CallToolResult
from mcp_server.artifacts import MAX_BYTES, result


def register(mcp, client, store, image_url):
    def convert(body):
        media = []
        def unpack(output):
            output = dict(output)
            if output.get("kind") == "multimodal":
                output["items"] = [unpack(item) for item in output.get("items", [])]
            for key in ("dataUrl", "annotated", "overlay"):
                url = output.pop(key, None)
                if url:
                    header, encoded = url.split(",", 1)
                    media.append((base64.b64decode(encoded), header[5:].split(";")[0], key))
            if "masks" in output:
                output["masks"] = [unpack(mask) for mask in output["masks"]]
            return output
        metadata = {**body, "output": unpack(body.get("output", {}))}
        return result("Inference completed", metadata, media, store())

    @mcp.tool()
    async def get_model_capabilities(model_id: str) -> dict[str, Any]:
        """Inspect tasks, parameter ranges, modalities, installation and runtime without loading weights."""
        from urllib.parse import urlencode
        return await client().get("/v1/models/capabilities?" + urlencode({"model": model_id}))

    @mcp.tool()
    async def analyze_image(image_path: str, model: str, question: str = "Describe this image.", params: dict | None = None) -> CallToolResult:
        """Ask a vision-language model about one image. Accepts local path, media data URL or artifact URI."""
        body = await client().post("/v1/tasks/run", {"task": "image-text-to-text", "model": model,
            "inputs": {"dataUrl": image_url(image_path), "text": question}, "params": params or {}})
        return convert(body)

    @mcp.tool()
    async def read_document(image_path: str, model: str, question: str = "What is the text content of this document?", top_k: int = 1) -> CallToolResult:
        """Answer a question about a scanned page using a document-question-answering model."""
        return convert(await client().post("/v1/tasks/run", {"task": "document-question-answering", "model": model,
            "inputs": {"dataUrl": image_url(image_path), "text": question}, "params": {"top_k": top_k}}))

    @mcp.tool()
    async def classify_image(image_path: str, model: str, labels: list[str] | None = None, top_k: int = 10) -> CallToolResult:
        """Classify an image. Supply labels for a zero-shot model such as CLIP."""
        task = "zero-shot-image-classification" if labels else "image-classification"
        return convert(await client().post("/v1/tasks/run", {"task": task, "model": model,
            "inputs": {"dataUrl": image_url(image_path), "text": ", ".join(labels or [])},
            "params": {} if labels else {"top_k": top_k}}))

    @mcp.tool()
    async def estimate_depth(image_path: str, model: str, invert: bool = False, blend: float = 0) -> CallToolResult:
        """Return a colorized monocular depth map; values are not guaranteed metric distances."""
        return convert(await client().post("/v1/tasks/run", {"task": "depth-estimation", "model": model,
            "inputs": {"dataUrl": image_url(image_path)}, "params": {"invert": invert, "blend": blend}}))

    @mcp.tool()
    async def edit_image(image_path: str, prompt: str, model: str, mask_path: str = "", params: dict | None = None) -> CallToolResult:
        """Run an image-to-image or inpainting checkpoint. White mask pixels indicate areas to replace."""
        inputs = {"dataUrl": image_url(image_path), "text": prompt}
        if mask_path:
            inputs["maskDataUrl"] = image_url(mask_path)
        return convert(await client().post("/v1/tasks/run", {"task": "inpainting" if mask_path else "image-to-image",
            "model": model, "inputs": inputs, "params": params or {}}))

    @mcp.tool()
    async def run_task(task: str, model: str, inputs: dict, params: dict | None = None, background: bool = False) -> CallToolResult:
        """Run a supported task. Inputs use text/dataUrl/maskDataUrl/points. Background returns a job ID."""
        body = await client().post("/v1/jobs" if background else "/v1/tasks/run",
            {"task": task, "model": model, "inputs": inputs, "params": params or {}})
        return result("Job queued", body, store=store()) if background else convert(body)

    @mcp.tool()
    async def get_job(job_id: str) -> CallToolResult:
        """Poll a background job; completed jobs return native output media."""
        body = await client().get("/v1/jobs/" + _job_id(job_id))
        if body.get("result"):
            if job_id not in completed_results:
                completed_results[job_id] = convert({**body["result"], "job_id": job_id, "status": body["status"]})
                if len(completed_results) > 100:
                    del completed_results[next(iter(completed_results))]
            return completed_results[job_id]
        return result("Job status", body, store=store())

    @mcp.tool()
    async def cancel_job(job_id: str) -> dict[str, Any]:
        """Cancel queued work or request cooperative interruption of running work. Native kernels may finish first."""
        return await client().post("/v1/jobs/" + _job_id(job_id) + "/cancel", {})

    @mcp.tool()
    async def upload_artifact(data_base64: str, mime_type: str, name: str = "Upload") -> dict[str, Any]:
        """Upload image/audio/text/JSON bytes and receive an artifact URI usable as media input."""
        if not (mime_type.startswith(("image/", "audio/", "text/")) or mime_type == "application/json"):
            raise ValueError("Supported uploads are images, audio, text and JSON")
        if len(data_base64) > MAX_BYTES * 4 // 3 + 4:
            raise ValueError("Upload exceeds 64 MiB")
        return store().save(base64.b64decode(data_base64, validate=True), mime_type, name)

    @mcp.tool()
    async def list_artifacts(limit: int = 20) -> dict[str, Any]:
        """List saved results and uploads, newest first."""
        return {"artifacts": store().list(limit)}

    @mcp.tool()
    async def get_artifact(artifact_id: str) -> CallToolResult:
        """Retrieve a saved result with native media and its metadata."""
        record, path = store().get(artifact_id)
        # Read an existing artifact without creating another history entry.
        from mcp.types import TextContent, ImageContent, AudioContent, ResourceLink
        from mcp_server.artifacts import INLINE_BYTES
        content = [TextContent(type="text", text=json.dumps(record))]
        mime = record["mime_type"]
        if path.stat().st_size <= INLINE_BYTES:
            if mime.startswith(("audio/", "image/")):
                cls = AudioContent if mime.startswith("audio/") else ImageContent
                content.append(cls(type="audio" if cls is AudioContent else "image", mimeType=mime, data=base64.b64encode(path.read_bytes()).decode()))
            elif mime.startswith("text/") or mime == "application/json":
                content.append(TextContent(type="text", text=path.read_text(encoding="utf-8")))
        content.append(ResourceLink(type="resource_link", uri=record["uri"], name=record["name"], mimeType=mime, size=record["bytes"]))
        return CallToolResult(content=content, structuredContent=record)

    @mcp.tool()
    async def prune_artifacts(older_than_days: int = 30) -> dict[str, Any]:
        """Permanently delete saved artifacts older than the chosen retention period. Explicit cleanup only."""
        return store().prune(older_than_days)

    @mcp.resource("zeroinfer://artifacts/{artifact_id}", mime_type="application/octet-stream")
    def artifact_resource(artifact_id: str) -> bytes:
        """Fetch artifact bytes by ID. MIME type is provided in the originating resource link."""
        _, path = store().get(artifact_id)
        return path.read_bytes()

    completed_results = {}


def _job_id(value):
    import re
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid job ID")
    return value
