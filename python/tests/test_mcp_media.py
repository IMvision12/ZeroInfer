"""Exercise real MCP serialization and HTTP contracts without downloading models."""
import asyncio
import base64
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from mcp_server import server
from mcp_server.artifacts import ArtifactStore, result
from api.server import create_app
from api.llm import resolve_llm, LLMNotLoaded, normalize_messages
from api import task_routes
from tasks.asr import ASRVariant
from capabilities import validate_params

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1ioAAAAASUVORK5CYII=")


def wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0\0" * 160)
    return buf.getvalue()


class McpOutputTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(server, "_output_dir", Path(self.temp.name))
        self.patch.start()
        self.image = Path(self.temp.name) / "input.png"
        self.image.write_bytes(PNG)

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    async def test_native_audio_serializes_with_resource_and_metadata(self):
        with patch.object(server._client, "post", AsyncMock(return_value=wav())):
            output = await server.text_to_speech("Hello", model="test/speech")
        wire = output.model_dump(mode="json")
        self.assertEqual([c["type"] for c in wire["content"]], ["text", "audio", "resource_link"])
        self.assertEqual(base64.b64decode(wire["content"][1]["data"]), wav())
        self.assertEqual(wire["structuredContent"]["duration_seconds"], 0.01)

    async def test_detection_keeps_exact_boxes_and_image(self):
        boxes = [{"label": "cat", "score": .923456, "box": {"x": .11, "y": .2, "w": .4, "h": .5}}]
        body = {"model": "test/detr", "data": boxes, "annotated": "data:image/png;base64," + base64.b64encode(PNG).decode()}
        with patch.object(server._client, "post", AsyncMock(return_value=body)):
            output = await server.detect_objects(str(self.image))
        self.assertEqual(output.structuredContent["detections"], boxes)
        self.assertIn("image", [c.type for c in output.content])

    async def test_fastmcp_registered_mixed_result_contract(self):
        body = {"model": "test/vlm", "output": {"kind": "multimodal", "items": [
            {"kind": "text", "text": "cat"}, {"kind": "image", "dataUrl": "data:image/png;base64," + base64.b64encode(PNG).decode()}]}}
        with patch.object(server._client, "post", AsyncMock(return_value=body)):
            output = await server.mcp.call_tool("analyze_image", {"image_path": str(self.image), "model": "test/vlm"})
        # FastMCP returns CallToolResult directly for explicit result annotations.
        self.assertEqual(output.structuredContent["output"]["items"][0]["text"], "cat")
        self.assertIn("image", [c.type for c in output.content])

    async def test_artifact_upload_read_and_path_traversal(self):
        store = server._store()
        first = store.save(PNG, "image/png")
        second = store.save(PNG, "image/png")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(server._read_media(first["uri"], "image")[0], PNG)
        with self.assertRaises(ValueError):
            store.get("../input")
        with patch.dict(os.environ, {"ZEROINFER_MCP_REMOTE": "1"}):
            with self.assertRaises(server.ZeroInferError):
                server._read_media(str(self.image), "image")
            self.assertEqual(server._read_media(first["uri"], "image")[0], PNG)

    async def test_existing_outputs_are_not_overwritten(self):
        with self.assertRaises(server.ZeroInferError):
            server._out_path("image.png", str(self.image))
        self.assertNotEqual(server._out_path("image.png", ""), server._out_path("image.png", ""))

    async def test_large_media_uses_resource_fallback(self):
        with patch("mcp_server.artifacts.INLINE_BYTES", 2):
            output = result("image", {}, [(PNG, "image/png", "preview")], server._store())
        self.assertEqual([c.type for c in output.content], ["text", "resource_link"])

    async def test_query_encoding_and_embedding_export(self):
        get = AsyncMock(return_value=[])
        with patch.object(server._client, "get", get):
            await server.search_models("cat & dog#1")
        self.assertIn("q=cat+%26+dog%231", get.call_args.args[0])
        body = {"model": "test/embed", "data": [{"embedding": [1., 0.]}, {"embedding": [0., 1.]}]}
        with patch.object(server._client, "post", AsyncMock(return_value=body)):
            out = await server.embed_text(["a", "b"], export_vectors=True)
        self.assertEqual(out["cosine_similarity"], [[1., 0.], [0., 1.]])
        _, path = server._store().get(out["artifact"]["id"])
        self.assertEqual(json.loads(path.read_text()), [[1., 0.], [0., 1.]])
        with self.assertRaises(server.ZeroInferError):
            await server.embed_text(["a"] * 129)

    async def test_retrieval_preserves_source_and_ranking(self):
        document = server._store().save(b"Cats sleep in sunny places.", "text/plain", "Pets")
        async def embeddings(path, body, **kwargs):
            return {"model": "test/embed", "data": [{"embedding": [1., 0.]} for _ in body["input"]]}
        with patch.object(server._client, "post", embeddings), patch("mcp.server.fastmcp.Context.report_progress", AsyncMock()):
            indexed = await server.mcp.call_tool("index_documents", {"artifact_ids": [document["id"]], "embedding_model": "test/embed"})
            # Plain dict tools are converted by FastMCP to (content, structured).
            data = indexed[1] if isinstance(indexed, tuple) else indexed.structuredContent
            found = await server.mcp.call_tool("search_documents", {"index_id": data["index_id"], "query": "Where do cats sleep?"})
            matches = (found[1] if isinstance(found, tuple) else found.structuredContent)["matches"]
        self.assertEqual(matches[0]["artifact_id"], document["id"])
        self.assertEqual(matches[0]["start_char"], 0)
        self.assertAlmostEqual(matches[0]["score"], 1)

    async def test_speech_workflow_returns_transcript_and_audio(self):
        async def post(path, body, **kwargs):
            if path.endswith("completions"):
                return {"model": "test/text", "choices": [{"message": {"content": "Hello back"}}]}
            return wav()
        audio = Path(self.temp.name) / "input.wav"
        audio.write_bytes(wav())
        with patch.object(server._client, "post", post), patch.object(server._client, "post_file", AsyncMock(return_value={"text": "Hello"})):
            out = await server.mcp.call_tool("speech_to_speech", {"audio_path": str(audio), "text_model": "test/text", "speech_model": "test/speech"})
        self.assertEqual(out.structuredContent["transcript"], "Hello")
        self.assertIn("audio", [c.type for c in out.content])

    async def test_streaming_text_reports_progress(self):
        async def events(*args, **kwargs):
            yield {"model": "test/text", "choices": [{"delta": {"content": "Hello"}}]}
            yield {"model": "test/text", "choices": [{"delta": {}, "finish_reason": "stop"}]}
        ctx = SimpleNamespace(report_progress=AsyncMock())
        with patch.object(server._client, "post_sse", events):
            out = await server.generate_text("Hi", stream=True, ctx=ctx)
        self.assertEqual(out["text"], "Hello")
        ctx.report_progress.assert_awaited_once()

    async def test_http_auth_and_mcp_media_roundtrip(self):
        import socket
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        token = "test-token-" + "x" * 32
        process = await asyncio.create_subprocess_exec(sys.executable, "-B", "-m", "mcp_server.server",
            "--transport", "streamable-http", "--port", str(port), "--output-dir", self.temp.name,
            cwd=str(Path(__file__).resolve().parents[1]), env={**os.environ, "ZEROINFER_MCP_TOKEN": token},
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        url = f"http://127.0.0.1:{port}/mcp"
        try:
            async with httpx.AsyncClient() as client:
                ready = False
                for _ in range(100):
                    try:
                        response = await client.get(url)
                        self.assertEqual(response.status_code, 401)
                        ready = True
                        break
                    except httpx.ConnectError:
                        await asyncio.sleep(.05)
                self.assertTrue(ready, "HTTP MCP server did not start")
            async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token}) as client:
                async with streamable_http_client(url, http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        upload = await session.call_tool("upload_artifact", {"data_base64": base64.b64encode(wav()).decode(), "mime_type": "audio/wav", "name": "Speech"})
                        self.assertFalse(upload.isError)
                        artifact = upload.structuredContent
                        output = await session.call_tool("get_artifact", {"artifact_id": artifact["id"]})
                        self.assertFalse(output.isError)
                        self.assertIn("audio", [c.type for c in output.content])
                        resource = await session.read_resource(artifact["uri"])
                        self.assertEqual(base64.b64decode(resource.contents[0].blob), wav())
        finally:
            if process.returncode is None:
                process.terminate()
            await process.wait()


class ApiContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_chat_rejects_media_instead_of_dropping_it(self):
        response = await self.client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]}]})
        self.assertEqual(response.status_code, 400)

    async def test_audio_format_options_are_not_silently_ignored(self):
        response = await self.client.post("/v1/audio/speech", json={"input": "test", "response_format": "mp3"})
        self.assertEqual(response.status_code, 400)
        response = await self.client.post("/v1/audio/transcriptions", data={"language": "en"}, files={"file": ("test.wav", wav(), "audio/wav")})
        self.assertEqual(response.status_code, 400)

    async def test_transcription_forwards_timestamps(self):
        media = AsyncMock(return_value=("test/asr", {"text": "hello", "segments": [{"start": 0, "end": .01, "text": "hello"}]}))
        with patch("api.routes._media_run", media):
            response = await self.client.post("/v1/audio/transcriptions", data={"response_format": "verbose_json"}, files={"file": ("test.wav", wav(), "audio/wav")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["segments"][0]["text"], "hello")
        self.assertTrue(media.call_args.args[4]["return_timestamps"])

    async def test_invalid_task_parameters_fail_before_inference(self):
        response = await self.client.post("/v1/tasks/run", json={"task": "depth-estimation", "model": "test/depth", "params": {"blend": 2}})
        self.assertEqual(response.status_code, 400)

    async def test_generation_seed_batch_and_validation(self):
        media = AsyncMock(return_value=("test/diffusion", {"kind": "image", "dataUrl": "data:image/png;base64," + base64.b64encode(PNG).decode()}))
        with patch("api.routes._media_run", media):
            response = await self.client.post("/v1/image/generation", json={"prompt": "lake", "model": "test/diffusion", "seed": 42, "n": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["seeds"], [42, 43])
        self.assertEqual(len(response.json()["data"]), 2)
        for payload in ({"steps": 0}, {"size": "nonsense"}, {"n": 9}, {"seed": -1}):
            response = await self.client.post("/v1/image/generation", json={"prompt": "lake", "model": "test/diffusion", **payload})
            self.assertEqual(response.status_code, 400, response.text)

    async def test_invalid_detection_and_segmentation_options(self):
        for path, payload in (("detection", {"threshold": {}}), ("detection", {"threshold": 2}),
                              ("segmentation", {"overlay_alpha": 999}), ("segmentation", {"points": [{"x": 2, "y": .5}]})):
            response = await self.client.post("/v1/image/" + path, json={"image": "data:image/png;base64," + base64.b64encode(PNG).decode(), **payload})
            self.assertEqual(response.status_code, 400, response.text)

    async def test_task_rejects_incompatible_model(self):
        with patch("routing.inspect_model", return_value={"pipeline_tag": "text-generation"}), patch("api.routes._media_run", AsyncMock()) as media:
            response = await self.client.post("/v1/tasks/run", json={"task": "depth-estimation", "model": "test/text", "inputs": {}})
        self.assertEqual(response.status_code, 400)
        media.assert_not_awaited()

    async def test_queued_job_cancel_does_not_stop_another_request(self):
        import runtime
        runtime.INFERENCE_LOCK_RAW.acquire()
        try:
            with patch("routing.inspect_model", return_value={"pipeline_tag": "image-text-to-text"}), patch("runtime.request_stop") as stop:
                response = await self.client.post("/v1/jobs", json={"task": "image-text-to-text", "model": "test/vlm", "inputs": {}})
                jid = response.json()["id"]
                await asyncio.sleep(.03)
                cancelled = await self.client.post(f"/v1/jobs/{jid}/cancel")
                self.assertEqual(cancelled.json()["status"], "cancelled")
                await asyncio.gather(task_routes.JOBS[jid]["_task"], return_exceptions=True)
                stop.assert_not_called()
                self.assertTrue(runtime.INFERENCE_LOCK_RAW.locked())
        finally:
            runtime.INFERENCE_LOCK_RAW.release()

    async def test_job_cancel_does_not_release_native_work_lock(self):
        import runtime
        started, finish = threading.Event(), threading.Event()
        def run(*args):
            started.set()
            finish.wait(3)
            return {"kind": "text", "text": "done"}
        engine = SimpleNamespace(run=run)
        with patch("routing.inspect_model", return_value={"pipeline_tag": "image-text-to-text"}), patch("runtime.engine", return_value=engine), patch("api.routes.viewer.publish"):
            response = await self.client.post("/v1/jobs", json={"task": "image-text-to-text", "model": "test/vlm", "inputs": {"text": "test"}})
            jid = response.json()["id"]
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(.01)
            self.assertTrue(started.is_set())
            cancelled = await self.client.post(f"/v1/jobs/{jid}/cancel")
            self.assertEqual(cancelled.json()["status"], "cancelling")
            self.assertTrue(runtime.INFERENCE_LOCK_RAW.locked())
            finish.set()
            await task_routes.JOBS[jid]["_task"]
            self.assertEqual(task_routes.JOBS[jid]["status"], "cancelled")
            self.assertFalse(runtime.INFERENCE_LOCK_RAW.locked())


class LogicTests(unittest.TestCase):
    def test_viewer_flattens_mixed_outputs_in_order(self):
        from api.viewer import items_for
        out = {"kind": "multimodal", "items": [{"kind": "text", "text": "Hello"},
            {"kind": "audio", "dataUrl": "data:audio/wav;base64," + base64.b64encode(wav()).decode()}]}
        self.assertEqual([item["type"] for item in items_for(out)], ["text", "audio"])

    def test_inpainting_passes_mask_seed_and_progress_callback(self):
        from PIL import Image
        from adapters.diffusers_pipeline import DiffusersAdapter
        progress = Mock()
        class Pipe:
            def __call__(self, prompt, callback_on_step_end=None, **kwargs):
                self.kwargs = kwargs
                self.prompt = prompt
                if callback_on_step_end:
                    callback_on_step_end(self, 0, 0, {})
                return SimpleNamespace(images=[Image.new("RGB", (8, 8))])
        adapter = DiffusersAdapter()
        adapter.task, adapter.pipe = "inpainting", Pipe()
        import runtime
        runtime.clear_stop()
        with patch("adapters.diffusers_pipeline.decode_image", return_value=Image.new("RGB", (8, 8))):
            out = adapter.run({"text": "new sky", "dataUrl": "input", "maskDataUrl": "mask"}, {"seed": 42, "_progress": progress})
        self.assertEqual(out["kind"], "image")
        self.assertEqual(adapter.pipe.kwargs["mask_image"].mode, "L")
        self.assertEqual(adapter.pipe.kwargs["generator"].initial_seed(), 42)
        progress.assert_called_once_with(1, 20)

    def test_segmentation_exports_individual_masks(self):
        from PIL import Image
        from tasks.image_segmentation import SegmentationVariant
        state = SimpleNamespace(pipe=Mock(return_value=[{"label": "cat", "score": .9, "mask": Image.new("L", (8, 8), 255)}]))
        with patch("tasks.image_segmentation.decode_image", return_value=Image.new("RGB", (8, 8))):
            out = SegmentationVariant().run(state, {"dataUrl": "x"}, {"export_masks": True})
        self.assertEqual(out["masks"][0]["label"], "cat")
        self.assertTrue(out["masks"][0]["dataUrl"].startswith("data:image/png;base64,"))

    def test_explicit_model_error_never_uses_fallback(self):
        eng = Mock()
        eng.get_cached_adapter.return_value = None
        eng.ensure_loaded.side_effect = RuntimeError("out of memory")
        with self.assertRaisesRegex(LLMNotLoaded, "out of memory"):
            resolve_llm(eng, "test/requested")
        eng.current_llm_id.assert_not_called()

    def test_asr_preserves_segment_boundaries(self):
        state = SimpleNamespace(info={"model_id": "test/whisper"}, pipe=Mock(return_value={"text": " hello", "chunks": [{"text": " hello", "timestamp": (0, None)}]}))
        with patch("tasks.asr.decode_audio", return_value=([0] * 160, 16000)):
            out = ASRVariant().run(state, {"dataUrl": "x"}, {"return_timestamps": True})
        self.assertEqual(out["segments"], [{"start": 0, "end": None, "text": "hello"}])
        self.assertEqual(out["text"], "hello")

    def test_nonfinite_parameters_rejected(self):
        for value in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                validate_params("depth-estimation", {"blend": value})


if __name__ == "__main__":
    unittest.main()
