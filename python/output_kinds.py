"""Canonical output shapes.

Every adapter returns a dict matching one of these shapes. Downstream UI code
only ever sees these kinds - adapters below the boundary can be as weird as
they need to be.
"""
from __future__ import annotations

import base64
import io
from typing import Iterable


def _encode_png(pil_image) -> str:
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _encode_wav(audio_array, sample_rate: int) -> str:
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, audio_array, sample_rate, format="WAV")
    return "data:audio/wav;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def boxes(items: Iterable[dict]) -> dict:
    """Detection. Each item: {label, score, box: [nx, ny, nw, nh]} in [0, 1]."""
    return {"kind": "boxes", "boxes": list(items)}


def masks(overlay_pil_rgba, legend: Iterable[dict]) -> dict:
    """Segmentation. `overlay_pil_rgba` is an RGBA PIL image the same size as the
    input; `legend` is [{label, color: 'rgb(...)' or '#rrggbb', score?}]."""
    return {
        "kind": "masks",
        "overlay": _encode_png(overlay_pil_rgba),
        "legend": list(legend),
    }


def labels(items: Iterable[dict]) -> dict:
    """Classification / zero-shot. Each item: {label, score}."""
    return {"kind": "labels", "labels": list(items)}


def text(s) -> dict:
    return {"kind": "text", "text": str(s or "")}


def image(pil_image) -> dict:
    return {"kind": "image", "dataUrl": _encode_png(pil_image)}


def audio(audio_array, sample_rate: int) -> dict:
    return {"kind": "audio", "dataUrl": _encode_wav(audio_array, sample_rate),
            "sample_rate": sample_rate, "duration_seconds": len(audio_array) / sample_rate}


def multimodal(*items: dict) -> dict:
    """Ordered mixed outputs; existing single-kind adapters remain compatible."""
    return {"kind": "multimodal", "items": list(items)}


def vector(vec) -> dict:
    """Feature extraction / embeddings. `vec` is a 1-D sequence of floats. The UI
    only shows the dimensionality and a short preview, so that's all we ship."""
    seq = [float(x) for x in vec]
    return {"kind": "vector", "dim": len(seq), "sample": seq[:8]}
