"""MCP server exposing ZeroInfer's local models to Claude and other LLM clients.

Wraps ZeroInfer's local HTTP API (see client.py for why this is a client, not an
engine embed) as MCP tools: detection, segmentation, transcription, speech,
image generation, text generation, embeddings, plus model discovery/install.

Requires the ZeroInfer desktop app to be running with its API switched on:
Settings -> Apps & integrations -> enable the local API server. The API is off by default -
it is the one thing ZeroInfer deliberately exposes, so it is opt-in - and with it
off there is nothing on port 11500 for these tools to talk to.

Registering with Claude Code: the app writes a launcher and shows the exact
`claude mcp add zeroinfer -- ...` command on that same Settings page. Both paths in
it are stable across app updates, which is the point of the generated launcher.

Conventions:
  - Media inputs accept local paths (stdio only), data URLs or artifact URIs.
  - Images and audio are returned as native MCP content, with resource links
    and structured metadata. Large media uses resource links only.
  - Embeddings can be exported as JSON artifacts without flooding context.
"""
from __future__ import annotations

import argparse
import base64
import io
import mimetypes
import os
import wave
import json
import uuid
from urllib.parse import urlencode
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP, Context
from mcp.types import CallToolResult
from mcp_server.artifacts import ArtifactStore, result, MAX_BYTES

from mcp_server.client import DEFAULT_URL, ZeroInferClient, ZeroInferError

INSTRUCTIONS = """Runs Hugging Face models locally through ZeroInfer.

Requires the ZeroInfer desktop app to be running with its local API enabled
(Settings -> Apps & integrations). The API is off by default, so this is the first thing
to check. Call `zeroinfer_status` if a tool fails - it reports whether the API is
reachable and which inference stack is installed.

Models are Hugging Face repo ids (e.g. "hustvl/yolos-tiny"). Most tools have a
small default model; `generate_image` has none, because diffusion weights are
gigabytes - pass an explicit `model`. Use `search_models` to find candidates
and `download_model` to fetch one ahead of time.
"""

mcp = FastMCP("zeroinfer", instructions=INSTRUCTIONS, max_request_body_size=96 * 1024 * 1024)

_client = ZeroInferClient()
_output_dir = Path.home() / "zeroinfer-outputs"


def _write_new(path, raw):
    if path is None:
        return
    with path.open("xb") as f:
        f.write(raw)


def _store():
    return ArtifactStore(_output_dir / "artifacts")


def _out_path(name: str, explicit: str | None) -> Path:
    if explicit and os.environ.get("ZEROINFER_MCP_REMOTE"):
        raise ZeroInferError("HTTP clients use artifact outputs; filesystem output paths are disabled")
    if explicit:
        p = Path(explicit).expanduser()
        if p.exists():
            raise ZeroInferError(f"Output already exists: {p}. Choose a new path.")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    _output_dir.mkdir(parents=True, exist_ok=True)
    p = Path(name)
    return _output_dir / f"{p.stem}-{uuid.uuid4().hex}{p.suffix}"


def _read_media(path: str, expect: str) -> tuple[bytes, str]:
    """Load a local image/audio file. Returns (bytes, mime)."""
    if path.startswith("zeroinfer://artifacts/"):
        _, p = _store().get(path.rsplit("/", 1)[1])
    elif path.startswith("data:"):
        header, encoded = path.split(",", 1)
        mime = header[5:].split(";", 1)[0]
        if ";base64" not in header or not mime.startswith(expect + "/"):
            raise ZeroInferError("Expected a base64 media data URL")
        if len(encoded) > MAX_BYTES * 4 // 3 + 4:
            raise ZeroInferError("Input exceeds 64 MiB")
        return base64.b64decode(encoded, validate=True), mime
    else:
        if os.environ.get("ZEROINFER_MCP_REMOTE"):
            raise ZeroInferError("HTTP clients must upload media or supply a data URL")
        p = Path(path).expanduser()
    if not p.is_file():
        raise ZeroInferError(f"No such file: {p}")
    mime, _ = mimetypes.guess_type(str(p))
    mime = mime or ("image/png" if expect == "image" else "audio/wav")
    if not mime.startswith(expect):
        raise ZeroInferError(f"{p.name} looks like {mime}, expected {expect}/*.")
    if p.stat().st_size > MAX_BYTES:
        raise ZeroInferError("Input exceeds 64 MiB")
    return p.read_bytes(), mime


def _image_data_url(path: str) -> str:
    raw, mime = _read_media(path, "image")
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def _decode_data_url(u: str) -> bytes:
    return base64.b64decode(u.split(",", 1)[1] if "," in u else u)


def _wav_duration(raw: bytes) -> float | None:
    """Duration from the RIFF header.

    Must stay stdlib-only. Importing soundfile here hangs the stdio server
    indefinitely: the tool call never returns and the client sees a dead
    transport. Nothing in this process should reach for the inference stack -
    the `mcp` extra doesn't install it.
    """
    try:
        with wave.open(io.BytesIO(raw)) as w:
            return round(w.getnframes() / float(w.getframerate()), 2)
    except Exception:
        return None


# --- discovery ---------------------------------------------------------------

@mcp.tool()
async def zeroinfer_status() -> dict[str, Any]:
    """Check that the ZeroInfer server is reachable and ready to run models.

    Reports the inference stack's readiness, any missing packages, the active
    accelerator (cpu/gpu), and which models are currently loaded in memory.
    Call this first when another tool fails unexpectedly.
    """
    health = await _client.health()
    status = await _client.get("/api/status", timeout=10.0)
    models = await _client.get("/api/models", timeout=10.0)
    return {
        "server": {"url": _client.base_url, "version": health.get("version")},
        "ready": status.get("ready"),
        "missing_packages": status.get("missing") or [],
        "accelerator": status.get("activeAccelerator"),
        "torch": status.get("torch"),
        "loaded_models": models.get("loaded") or [],
        "current_llm": models.get("currentLlm"),
    }


@mcp.tool()
async def list_models() -> dict[str, Any]:
    """List the models ZeroInfer can serve right now.

    `loaded` are resident in memory; `available` lists loaded or installed
    API models. Architecture support alone does not guarantee a successful load.
    """
    loaded = await _client.get("/api/models", timeout=10.0)
    served = await _client.get("/v1/models", timeout=10.0)
    installed = await _client.get("/api/hf/installed", timeout=10.0)
    return {
        "loaded": loaded.get("loaded") or [],
        "current_llm": loaded.get("currentLlm"),
        "available": [m["id"] for m in (served.get("data") or [])],
        "installed": [
            {"id": mid, "task": (meta or {}).get("task")}
            for mid, meta in (installed or {}).items()
        ],
    }


@mcp.tool()
async def search_models(query: str = "", task: str = "", limit: int = 10) -> list[dict]:
    """Search Hugging Face for models ZeroInfer can actually run.

    Results are filtered by architecture support; loading still depends on
    hardware, access permissions, and installed runtime versions. Narrow with `task`, e.g. "object-detection",
    "image-segmentation", "automatic-speech-recognition", "text-to-speech",
    "text-to-image", "text-generation", "feature-extraction".
    """
    qs = "?" + urlencode({"q": query, "task": task})
    body = await _client.get("/api/hf/search" + qs, timeout=60.0)
    items = body.get("items") if isinstance(body, dict) else body
    out = []
    for m in (items or [])[: max(1, min(limit, 50))]:
        out.append({
            "id": m.get("id"),
            "task": m.get("task"),
            "size": m.get("size"),
            "downloads": m.get("dl"),
            "installed": m.get("installed"),
            "description": (m.get("desc") or "")[:160],
        })
    return out


@mcp.tool()
async def download_model(model_id: str, ctx: Context = None) -> dict[str, Any]:
    """Download a model's weights into the local cache.

    Idempotent - an already-cached model returns immediately. Large models take
    minutes. Downloading ahead of time is also the reliable way to prepare a
    diffusion model for `generate_image` on Windows.
    """
    async def progress(evt):
        if ctx:
            await ctx.report_progress(progress=float(evt.get("done") or 0), total=evt.get("total"), message=str(evt.get("message") or "Downloading model"))
    info = await _client.download(model_id, on_progress=progress)
    return {
        "model": model_id,
        "downloaded_bytes": info.get("bytes"),
        "path": info.get("path"),
    }


# --- vision ------------------------------------------------------------------

@mcp.tool()
async def detect_objects(image_path: str, labels: list[str] | None = None,
                         threshold: float | None = None,
                         model: str = "", output_path: str = "") -> CallToolResult:
    """Detect objects in an image, show the boxes drawn on it, and list what was found.

    Pass `labels` (e.g. ["a cat", "a traffic light"]) to run *open-vocabulary*
    detection, which finds arbitrary things described in words. Omit it to use
    a fixed-vocabulary detector over the 80 COCO classes.

    Returns the annotated image plus each object's label, confidence, and box.
    Boxes are normalized to [0,1] as x/y/w/h with the origin top-left, so they
    are resolution-independent.
    """
    # `annotated` is opt-in on the endpoint - the engine draws the boxes either
    # way, but only sends the PNG back when asked. Not asking meant this tool
    # returned bare coordinates and the caller had no way to *see* the result:
    # it had to talk the user through uploading the image somewhere else to get a
    # picture of a detection it had already performed.
    payload: dict[str, Any] = {"image": _image_data_url(image_path), "annotated": True}
    if model:
        payload["model"] = model
    if threshold is not None:
        payload["threshold"] = threshold
    if labels:
        payload["labels"] = labels

    body = await _client.post("/v1/image/detection", payload)
    objects = body.get("data") or []
    found = body.get("model")

    if objects:
        lines = "\n".join(
            "  {label}  {pct:.1f}%   box x={x:.3f} y={y:.3f} w={w:.3f} h={h:.3f}".format(
                label=o.get("label"),
                pct=float(o.get("score") or 0) * 100,
                **{k: float((o.get("box") or {}).get(k) or 0) for k in ("x", "y", "w", "h")},
            )
            for o in objects
        )
        text = f"Detected {len(objects)} object(s) with {found}:\n{lines}"
    else:
        text = f"{found} found nothing above the confidence threshold."

    annotated = body.get("annotated")
    if not annotated:
        return result(text, {"model": found, "detections": objects}, store=_store())

    png = _decode_data_url(annotated)
    dest = _out_path(f"detection-{Path(image_path).stem}.png", output_path) if output_path else None
    _write_new(dest, png)
    return result(text, {"model": found, "detections": objects, "coordinate_format": "normalized_xywh", "path": str(dest) if dest else None},
                  [(png, "image/png", "Detection")], _store())


@mcp.tool()
async def segment_image(image_path: str, model: str = "",
                        output_path: str = "", params: dict | None = None, points: list[dict] | None = None, export_masks: bool = False) -> CallToolResult:
    """Segment an image into labelled regions and show the result.

    Handles semantic, instance, and panoptic segmentation (SegFormer,
    Mask2Former, OneFormer, ...) and SAM-style automatic mask generation - the
    model you pass decides which. SAM produces unlabelled "region N" masks
    because it has no class vocabulary.

    Returns a colour-coded overlay image plus the legend mapping colours to
    classes.
    """
    payload: dict[str, Any] = {"image": _image_data_url(image_path)}
    if model:
        payload["model"] = model
    allowed_params = {"overlay_alpha", "legend_min_pct", "points_per_batch", "min_mask_pct", "max_masks", "oneformer_mode"}
    if params and set(params) - allowed_params:
        raise ZeroInferError("Unsupported segmentation parameters: " + ", ".join(sorted(set(params) - allowed_params)))
    payload.update(params or {})
    payload["export_masks"] = export_masks
    if points:
        payload["points"] = points
    body = await _client.post("/v1/image/segmentation", payload)

    overlay = _decode_data_url(body["overlay"])
    dest = _out_path(f"segmentation-{Path(image_path).stem}.png", output_path) if output_path else None
    _write_new(dest, overlay)

    legend = body.get("legend") or []
    media = [(overlay, "image/png", "Segmentation overlay")]
    for mask in body.get("masks", []):
        media.append((_decode_data_url(mask["dataUrl"]), "image/png", mask.get("label", "Mask")))
    return result(f"Segmented {len(legend)} regions", {"model": body.get("model"), "legend": legend, "path": str(dest) if dest else None}, media, _store())


@mcp.tool()
async def generate_image(prompt: str, model: str, size: str = "",
                         steps: int | None = None,
                         guidance_scale: float | None = None,
                         negative_prompt: str = "",
                         output_path: str = "",
                         ensure_downloaded: bool = True, seed: int | None = None, n: int = 1) -> CallToolResult:
    """Generate an image from a text prompt using a local diffusion model.

    `model` is required - diffusion weights are gigabytes, so there is no
    default. Try "stabilityai/sd-turbo" (fast, 1-4 steps) or search for
    text-to-image models.

    `size` is "WIDTHxHEIGHT" (e.g. "512x512"); omit it to use the model's
    native resolution. `ensure_downloaded` pre-fetches the weights through
    ZeroInfer's own downloader, which is required on Windows: diffusers builds
    its download patterns with os.path.join, so loading an uncached pipeline
    there silently skips every component config.json and fails.
    """
    if not 1 <= n <= 4:
        raise ZeroInferError("n must be between 1 and 4")
    if n > 1 and output_path:
        raise ZeroInferError("Use the artifact results for multiple images; output_path is for one image")
    if ensure_downloaded:
        await _client.download(model)

    payload: dict[str, Any] = {"prompt": prompt, "model": model}
    if size:
        payload["size"] = size
    if steps is not None:
        payload["steps"] = steps
    if guidance_scale is not None:
        payload["guidance_scale"] = guidance_scale
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt

    payload.update(n=n, seed=seed)
    body = await _client.post("/v1/image/generation", payload)
    raw = base64.b64decode(body["data"][0]["b64_json"])
    stem = "".join(ch if ch.isalnum() else "-" for ch in prompt.lower())[:40].strip("-")
    dest = _out_path(f"{stem or 'image'}.png", output_path) if output_path else None
    _write_new(dest, raw)
    media = [(base64.b64decode(item["b64_json"]), "image/png", f"Generated image {i+1}") for i, item in enumerate(body["data"])]
    return result("Generated images", {"model": body.get("model"), "seeds": body.get("seeds"), "parameters": payload}, media, _store())


# --- audio -------------------------------------------------------------------

@mcp.tool()
async def transcribe_audio(audio_path: str, model: str = "",
                           timestamps: bool = False) -> dict[str, Any]:
    """Transcribe speech from an audio file to text.

    Defaults to Whisper. Set `timestamps` to get a segment-by-segment
    transcript instead of one block of text.
    """
    raw, mime = _read_media(audio_path, "audio")
    data = {"response_format": "verbose_json" if timestamps else "json"}
    if model:
        data["model"] = model
    body = await _client.post_file("/v1/audio/transcriptions",
                                   filename=Path(audio_path).name,
                                   content=raw, mime=mime, data=data)
    out = {"text": body.get("text", ""), "model": body.get("model")}
    if timestamps:
        out["duration_seconds"] = body.get("duration")
        out["segments"] = body.get("segments") or []
    return out


@mcp.tool()
async def text_to_speech(text: str, voice: str = "", model: str = "",
                         output_path: str = "") -> CallToolResult:
    """Synthesize speech from text and save it as a WAV file.

    Returns native MCP audio, a resource link, and the saved WAV path. `voice` accepts OpenAI's names (alloy, echo, fable, onyx, nova,
    shimmer) and only affects SpeechT5; other TTS models have a fixed voice.
    Output is always WAV.
    """
    payload: dict[str, Any] = {"input": text}
    if voice:
        payload["voice"] = voice
    if model:
        payload["model"] = model
    reply = await _client.post("/v1/audio/speech", payload, with_headers=True)
    raw, headers = reply if isinstance(reply, tuple) else (reply, {})
    if not isinstance(raw, (bytes, bytearray)):
        raise ZeroInferError(f"Expected WAV bytes, got {type(raw).__name__}")
    stem = "".join(ch if ch.isalnum() else "-" for ch in text.lower())[:40].strip("-")
    dest = _out_path(f"{stem or 'speech'}.wav", output_path) if output_path else None
    _write_new(dest, raw)
    return result(text, {"path": str(dest) if dest else None, "model": headers.get("x-zeroinfer-model", model or None), "duration_seconds": _wav_duration(bytes(raw))},
                  [(bytes(raw), "audio/wav", "Speech")], _store())


# --- text --------------------------------------------------------------------

@mcp.tool()
async def generate_text(prompt: str, model: str = "", system: str = "",
                        max_tokens: int = 512,
                        temperature: float | None = None, messages: list[dict] | None = None,
                        stream: bool = False, ctx: Context = None) -> dict[str, Any]:
    """Run a prompt through a local LLM loaded in ZeroInfer.

    With no `model`, uses whichever LLM is currently loaded. Useful for running
    a small on-device model, comparing its output against your own, or keeping
    a prompt entirely local.
    """
    messages = ([{"role": "system", "content": system}] if system else []) + (messages or []) + [{"role": "user", "content": prompt}]
    payload: dict[str, Any] = {"messages": messages, "max_tokens": max_tokens}
    if model:
        payload["model"] = model
    if temperature is not None:
        payload["temperature"] = temperature
    if not 1 <= max_tokens <= 32768:
        raise ZeroInferError("max_tokens must be between 1 and 32768")
    if temperature is not None and not 0 <= temperature <= 2:
        raise ZeroInferError("temperature must be between 0 and 2")
    if stream:
        payload["stream"] = True
        text, actual_model, finish, chunks = "", model, None, 0
        async for event in _client.post_sse("/v1/chat/completions", payload):
            _client._raise_for_body(event)
            actual_model = event.get("model", actual_model)
            for choice in event.get("choices", []):
                fragment = choice.get("delta", {}).get("content") or ""
                text += fragment
                finish = choice.get("finish_reason") or finish
                if fragment and ctx:
                    chunks += 1
                    await ctx.report_progress(chunks, message=fragment)
        return {"model": actual_model, "text": text, "finish_reason": finish, "usage": None}
    body = await _client.post("/v1/chat/completions", payload)
    choice = body["choices"][0]
    return {
        "model": body.get("model"),
        "text": choice["message"].get("content") or "",
        "finish_reason": choice.get("finish_reason"),
        "usage": body.get("usage"),
    }


@mcp.tool()
async def embed_text(texts: list[str], model: str = "", export_vectors: bool = False, similarity: bool = True) -> dict[str, Any]:
    """Embed text locally and report the vectors' shape and similarity.

    The raw vectors are deliberately not returned - hundreds of floats per
    string are unreadable and would flood the context. For two or more inputs
    this returns the pairwise cosine similarity matrix, which is what the
    vectors are usually for.
    """
    if len(texts) > 128 or sum(len(t) for t in texts) > 1_000_000:
        raise ZeroInferError("Limit inputs to 128 texts and one million characters")
    if not texts:
        raise ZeroInferError("`texts` must contain at least one string.")
    payload: dict[str, Any] = {"input": texts}
    if model:
        payload["model"] = model
    body = await _client.post("/v1/embeddings", payload)
    vectors = [d["embedding"] for d in body["data"]]
    out: dict[str, Any] = {
        "model": body.get("model"),
        "count": len(vectors),
        "dimensions": len(vectors[0]) if vectors else 0,
        "usage": body.get("usage"),
    }
    if export_vectors:
        out["artifact"] = _store().save(json.dumps(vectors).encode(), "application/json", "Embedding vectors", {"model": body.get("model")})
    if similarity and len(vectors) > 1:
        # Embeddings come back L2-normalized, so the dot product is the cosine.
        out["cosine_similarity"] = [
            [round(sum(a * b for a, b in zip(u, v)), 4) for v in vectors]
            for u in vectors
        ]
    return out


from mcp_server.extensions import register
register(mcp, lambda: _client, _store, _image_data_url)
from mcp_server.workflows import register as register_workflows
register_workflows(mcp, lambda: _client, _store, _read_media, _image_data_url)


def main() -> None:
    global _client, _output_dir
    p = argparse.ArgumentParser(
        prog="zeroinfer-mcp",
        description="Expose a running ZeroInfer server to LLM clients over MCP (stdio).",
    )
    p.add_argument("--url", default=os.environ.get("ZEROINFER_URL", DEFAULT_URL),
                   help=f"ZeroInfer server base URL (default {DEFAULT_URL}).")
    p.add_argument("--output-dir",
                   default=os.environ.get("ZEROINFER_MCP_OUTPUT_DIR", str(_output_dir)),
                   help="Where generated images and audio are written.")
    p.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=11501)
    args = p.parse_args()

    _client = ZeroInferClient(args.url)
    _output_dir = Path(args.output_dir).expanduser()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        from mcp_server.http_transport import serve
        serve(mcp, args.host, args.port)


if __name__ == "__main__":
    main()
