"""depth-estimation - single image → colorized depth map.

Works for DPT, GLPN, ZoeDepth, MiDaS, Depth Anything v1/v2, Depth Pro - every
HF model tagged `depth-estimation`. The pipeline returns the depth as either
a grayscale PIL image (newer transformers) or a torch tensor; we accept both
and colorize via a turbo/plasma colormap so the UI shows a finished image."""
from __future__ import annotations

from .base import TaskHandler, TaskVariant
from io_utils import decode_image
import output_kinds as ok

def _to_array(depth):
    """Normalize a depth result (PIL grayscale, torch.Tensor, np.ndarray) to a
    2-D float32 numpy array."""
    import numpy as np
    if hasattr(depth, "convert") and hasattr(depth, "size"):
        return np.array(depth.convert("F"), dtype=np.float32)
    arr = np.asarray(depth, dtype=np.float32)
    while arr.ndim > 2:
        arr = arr.squeeze(0) if arr.shape[0] == 1 else arr.mean(axis=0)
    return arr

def _resize_to(arr, w, h):
    import numpy as np
    from PIL import Image
    if arr.shape == (h, w):
        return arr
    return np.array(Image.fromarray(arr).resize((w, h), Image.BILINEAR), dtype=np.float32)

def _colorize(arr01):
    """Map a 2-D array in [0,1] to RGB via matplotlib's turbo if available,
    else a hand-rolled plasma ramp. Returns a uint8 (H,W,3) array."""
    import numpy as np
    try:
        import matplotlib.cm as cm
        rgba = cm.get_cmap("turbo")(arr01)
        return (rgba[..., :3] * 255).astype(np.uint8)
    except Exception:
        stops = np.array([
            [13, 8, 135], [126, 3, 168], [203, 70, 121], [248, 149, 64], [240, 249, 33],
        ], dtype=np.float32)
        idx = arr01 * (stops.shape[0] - 1)
        i0 = np.clip(idx.astype(np.int32), 0, stops.shape[0] - 2)
        f = (idx - i0)[..., None]
        rgb = stops[i0] * (1 - f) + stops[i0 + 1] * f
        return rgb.astype(np.uint8)

class DepthEstimationVariant(TaskVariant):
    name = "standard"

    def can_handle(self, info, inputs):
        return bool(inputs.get("dataUrl"))

    def run(self, state, inputs, params):
        import numpy as np
        from PIL import Image
        img = decode_image(inputs["dataUrl"])
        W, H = img.size
        result = state.pipe(img)
        depth = None
        if isinstance(result, dict):
            depth = result.get("depth")
            if depth is None:
                depth = result.get("predicted_depth")
        if depth is None:
            raise ValueError("Depth pipeline returned no depth field")

        arr = _resize_to(_to_array(depth), W, H)
        lo, hi = float(arr.min()), float(arr.max())
        norm = np.zeros_like(arr) if hi - lo < 1e-6 else (arr - lo) / (hi - lo)
        if bool(params.get("invert", False)):
            norm = 1.0 - norm
        rgb = _colorize(norm)
        colored = Image.fromarray(rgb, "RGB")

        blend = float(params.get("blend", 0.0))
        if blend > 0:
            base = img.convert("RGBA")
            top = colored.convert("RGBA")
            top.putalpha(int(255 * min(max(blend, 0.0), 1.0)))
            base.alpha_composite(top)
            colored = base.convert("RGB")
        return ok.image(colored)

class DepthEstimationTask(TaskHandler):
    name = "depth-estimation"
    output_kind = "image"
    default_params = {"invert": False, "blend": 0.0}
    variants = [DepthEstimationVariant()]
