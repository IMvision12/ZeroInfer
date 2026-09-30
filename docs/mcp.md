# MCP capabilities

ZeroInfer's MCP process calls the desktop app's optional local API. It does not
load a second inference engine. Enable the API under Settings → Apps & integrations.
Restart the app and the client's MCP connection after upgrading. MCP requires
`mcp>=1.30,<2`; the managed runtime installs this range.

## Results and files

Image and audio tools return native MCP content, `structuredContent`, readable text
metadata and resource links. Whether a client displays an audio player depends on
the client. Structured detection results preserve exact confidence values and
normalized `x/y/width/height` coordinates. Segmentation can export individual masks
with `export_masks=true`. Document answers preserve scores and token offsets when
the model provides them; these offsets are not page coordinates.

The engine also supports ordered `kind: multimodal` results. Existing adapters
continue returning their existing single output kinds; the shared MCP converter
and desktop renderer support both.

Artifacts have unique IDs, MIME types, byte sizes, timestamps and model metadata.
PNG dimensions and WAV duration/channel/sample-rate metadata are included.
Generated media lives in `<output-dir>/artifacts`, defaulting to
`~/zeroinfer-outputs/artifacts`. There is no automatic deletion. Use
`prune_artifacts(older_than_days=30)` for explicit cleanup. Explicit `output_path`
exports are outside managed retention and never overwrite an existing file.

Media input arguments accept local paths in stdio mode, base64 data URLs, or
`zeroinfer://artifacts/{id}` URIs. HTTP mode accepts data URLs and uploaded
artifacts, and disables arbitrary filesystem input/output paths. A chat attachment
must be transferred by the client; mentioning it does not upload its bytes.

Uploads/artifacts are limited to 64 MiB each. A result inlines at most 8 MiB of
combined image/audio data; larger outputs remain available through resources.
Use `get_artifact` for previews and `resources/read` for full bytes.

## Model parameters

`get_model_capabilities(model_id)` reports the task, modalities, shared parameter
definitions, model-specific availability, known diffusion defaults, installation
and runtime status. Architecture support is not a promise that a model fits in
memory or that gated weights are accessible. Hardware fit and language support
are not automatically benchmarked.

`python/task_parameters.json` is the canonical parameter definition for the
workspace and task API. `npm run build:renderer` generates the browser copy.
Hyperparameters remain in the model workspace, not global Settings.

Examples of MCP tool arguments:

```json
{"tool":"analyze_image","arguments":{"image_path":"zeroinfer://artifacts/ARTIFACT_ID","model":"MODEL_ID","question":"What is in this image?"}}
{"tool":"generate_image","arguments":{"prompt":"A mountain lake","model":"MODEL_ID","seed":42,"n":2,"size":"512x512"}}
{"tool":"edit_image","arguments":{"image_path":"INPUT","mask_path":"MASK","model":"INPAINTING_MODEL_ID","prompt":"Replace the sky","params":{"seed":42,"strength":0.8}}}
{"tool":"embed_text","arguments":{"texts":["first","second"],"export_vectors":true,"similarity":false}}
```

These are illustrative tool calls; select installed, task-compatible model IDs.
Image editing requires a checkpoint tagged for image-to-image or inpainting.
White pixels in an inpainting mask identify the region to replace. Seeded runs
are reproducible only within the limitations of the model, device and runtime.
Batch image generation accepts 1–4 images and increments the seed per image.

Transcription timestamps are forwarded to the ASR model and preserve actual
segment boundaries when available. Models without timestamp support can reject
the option. Unsupported language/prompt/temperature overrides and non-WAV speech
formats produce explicit errors. Named voice selection currently maps to SpeechT5
speaker indices and is rejected for other models.

`generate_text` accepts conversation history through `messages`; `prompt` is
appended as the next user message. `stream=true` sends text fragments as MCP
progress messages before returning the final response. Clients may choose not to
display progress; token usage is unavailable in this mode. The chat-completions
API rejects non-text content. Use `analyze_image`/`run_task` for vision inputs.

## Jobs and workflows

`run_task(task, model, inputs, params, background=true)` returns a job ID.
Poll `get_job`, and use `cancel_job` to cancel queued work or request interruption
of running work. The native inference lock stays held until the worker stops.
Transformers text generation and supported diffusers pipelines check cancellation
between tokens/steps; other native operations may finish before cancellation is
observed. Diffusion jobs expose step progress. Downloads expose byte progress and
request cancellation when their connection closes.

Jobs are in memory: at most 16 active jobs and 100 records, and they do not survive
an API restart. Completed outputs become persistent artifacts when retrieved
through MCP. Repeated polling reuses cached result artifacts within that MCP process.

- `speech_to_speech` is a batch transcription → text response → speech workflow,
  returning both text and native audio. It is not a realtime voice session.
- `analyze_frames` handles 1–16 extracted video frames, independently and in order,
  with optional timestamps. It does not decode video files, track objects across
  frames, generate videos or perform temporal video-model inference.
- `index_documents` accepts up to 32 UTF-8 text artifacts, each up to one million
  bytes, and produces at most 512 chunks. `search_documents` returns source IDs,
  character offsets, excerpts and cosine scores. Extract PDF/scanned text first;
  this tool is retrieval, not an automatic PDF parser or answer generator.
- `embed_text` accepts at most 128 strings / one million characters. Similarity
  matrices are optional; vectors can be exported without flooding model context.

## Optional HTTP transport

Stdio remains the default. For a client supporting Streamable HTTP with bearer
authentication, set a random `ZEROINFER_MCP_TOKEN` of at least 32 characters in the
server environment, then run the launcher with:

```text
--transport streamable-http --host 127.0.0.1 --port 11501
```

The endpoint is `http://127.0.0.1:11501/mcp`. Supply
`Authorization: Bearer <token>`. The bearer token is never passed in a command-line
argument. For access from another machine, use an HTTPS reverse proxy with an
explicit allowed-host configuration. The desktop inference API remains loopback
only and should not be exposed directly. This implementation provides static bearer
authentication, not an OAuth authorization server; clients requiring OAuth need
an appropriate gateway. No tunnel or public deployment is created automatically.

For a reverse proxy, set `ZEROINFER_MCP_ALLOWED_HOSTS` to a comma-separated list
of accepted Host headers, for example `mcp.example.com,127.0.0.1:*`. If a client
sends Origin headers, configure the exact accepted origins through
`ZEROINFER_MCP_ALLOWED_ORIGINS` (for example `https://mcp.example.com`). Host/origin
validation remains enabled in addition to bearer authentication.

## Verification

`python -B -m unittest discover -s python/tests -v` covers real stdio/HTTP MCP
handshakes, authenticated media upload/resource retrieval, serialized multimodal
results, timestamps, parameter validation, cancellation locking and retrieval
contracts. Inference is mocked for these tests; model-specific quality, memory
requirements and client playback support require separate real-model testing.
