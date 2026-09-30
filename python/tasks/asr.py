"""automatic-speech-recognition - one variant that decides chunking from
actual audio duration and preserves structured timestamps when requested."""
from __future__ import annotations

from .base import TaskHandler, TaskVariant
from io_utils import decode_audio
import output_kinds as ok

class ASRVariant(TaskVariant):
    """Single variant: decode audio, compute duration, pass through the user's
    chunking / timestamp params. Earlier versions had separate short/long
    variants keyed on an `inputs.duration_seconds` field that the JS side
    never actually sent - LongAudioVariant was dead code and the user's
    chunk / timestamp params were silently ignored."""
    name = "standard"

    def can_handle(self, info, inputs):
        return bool(inputs.get("dataUrl"))

    def run(self, state, inputs, params):
        audio, sr = decode_audio(inputs["dataUrl"])
        duration_s = float(len(audio)) / float(sr) if sr else 0.0
        want_timestamps = bool(params.get("return_timestamps", False))
        whisper_mode = (params.get("whisper_mode") or "transcribe").strip().lower()
        is_whisper = "whisper" in (state.info.get("model_id") or "").lower()

        kwargs = {}
        if duration_s > 30:
            kwargs["chunk_length_s"] = int(params.get("chunk_length_s", 30))
            kwargs["stride_length_s"] = int(params.get("stride_length_s", 5))
        if want_timestamps:
            kwargs["return_timestamps"] = True
        if is_whisper and whisper_mode == "translate":
            kwargs.setdefault("generate_kwargs", {})["task"] = "translate"

        result = state.pipe({"array": audio, "sampling_rate": sr}, **kwargs)
        text = (result.get("text") or "").strip()
        chunks = result.get("chunks")
        if want_timestamps:
            segments = []
            for c in chunks or []:
                start, end = c.get("timestamp") or (None, None)
                segments.append({"start": start, "end": end, "text": (c.get("text") or "").strip()})
            return {**ok.text(text), "segments": segments, "duration_seconds": duration_s}
        return ok.text(text)

class ASRTask(TaskHandler):
    name = "automatic-speech-recognition"
    output_kind = "text"
    default_params = {"chunk_length_s": 30, "stride_length_s": 5}
    variants = [ASRVariant()]
