"""mask-generation - SAM family (v1, SAM 2, SAM 2.1, SAM 3).

Automatic grid-sampling mode: the pipeline samples a uniform grid of point
prompts and produces one mask per significant region. SAM itself doesn't
assign class labels, so we synthesize "region N" entries in the legend and
reuse the existing `masks` output kind the segmentation tab already knows
how to render."""
from __future__ import annotations

from .base import TaskHandler, TaskVariant, LoadedPipeline
from ._render import composite_masks, encode_png_data_url
from io_utils import decode_image
import output_kinds as ok

REGION_PALETTE = [
    (255, 99, 71),  (30, 144, 255), (50, 205, 50),  (255, 215, 0),
    (186, 85, 211), (0, 206, 209),  (255, 140, 0),  (220, 20, 60),
    (46, 139, 87), (138, 43, 226),  (0, 191, 255),  (255, 105, 180),
    (124, 252, 0), (255, 69, 0),    (0, 250, 154),  (255, 20, 147),
]

def info_model_type(state):
    """Pull the transformers model_type from a LoadedPipeline for error messages."""
    info = getattr(state, "info", None) or {}
    return info.get("model_type") or info.get("pipeline_tag") or "unknown"

def _extract_masks(raw):
    """SAM pipelines return either a dict `{masks, scores}` or a list with
    one dict per image. Normalize to (masks, scores).

    CANNOT use `x or []` here - when the pipeline hands back a torch.Tensor
    the truthiness check raises "Boolean value of Tensor with more than one
    value is ambiguous". Explicit None check instead."""
    def _pair(d):
        m = d.get("masks")
        s = d.get("scores")
        return (m if m is not None else []), (s if s is not None else [])
    if isinstance(raw, dict):
        return _pair(raw)
    if isinstance(raw, list) and len(raw) > 0:
        head = raw[0]
        if isinstance(head, dict):
            return _pair(head)
    return [], []

class AutoMaskGenVariant(TaskVariant):
    """Grid sampling - default for SAM v1/2/2.1/3 when the user just gives an
    image with no point/box prompts."""
    name = "auto-mask-generation"

    def can_handle(self, info, inputs):
        return bool(inputs.get("dataUrl"))

    def run(self, state, inputs, params):
        import numpy as np
        from PIL import Image

        img = decode_image(inputs["dataUrl"])
        W, H = img.size
        ppb = int(params.get("points_per_batch", 64))
        min_pct = float(params.get("min_mask_pct", 0.5))
        alpha = int(params.get("overlay_alpha", 140))
        max_masks = int(params.get("max_masks", 64))

        if state.pipe is None:
            raise ValueError(
                f"Auto-grid mask generation isn't available for this SAM variant "
                f"(model_type={info_model_type(state)!r}) in the installed transformers version. "
                f"Click the image to add point prompts and run again - point-prompt mode is supported."
            )

        raw = state.pipe(img, points_per_batch=ppb)
        masks_list, scores_list = _extract_masks(raw)

        items = []
        for i, m in enumerate(masks_list):
            arr = np.asarray(m, dtype=bool)
            if arr.ndim == 3:
                arr = arr.squeeze()
            if arr.shape[:2] != (H, W):
                pil = Image.fromarray((arr.astype(np.uint8) * 255))
                pil = pil.resize((W, H), Image.NEAREST)
                arr = np.array(pil) > 127
            n = int(arr.sum())
            score = float(scores_list[i]) if i < len(scores_list) else None
            items.append((n, score, arr))

        items.sort(key=lambda t: -t[0])
        items = items[:max_masks]

        total = max(1, W * H)
        overlay_arr = np.zeros((H, W, 4), dtype=np.uint8)
        legend = []
        exported_masks = []

        for (n, score, arr) in items:
            pct = 100.0 * n / total
            if pct < min_pct:
                continue
            rgb = REGION_PALETTE[len(legend) % len(REGION_PALETTE)]
            overlay_arr[arr] = [rgb[0], rgb[1], rgb[2], alpha]
            if params.get("export_masks"):
                exported_masks.append({"label": f"region {len(exported_masks)+1}", "dataUrl": encode_png_data_url(Image.fromarray(arr.astype(np.uint8) * 255, mode="L"))})
            legend.append({
                "label": f"region {len(legend) + 1}",
                "color": f"rgb({rgb[0]},{rgb[1]},{rgb[2]})",
                "coverage": round(pct, 1),
                "score": score,
            })

        overlay = Image.fromarray(overlay_arr, mode="RGBA")
        annotated = composite_masks(img, overlay)
        result = ok.masks(overlay, legend)
        if params.get("export_masks"):
            result["masks"] = exported_masks
        result["annotated"] = encode_png_data_url(annotated)
        return result

class PointPromptVariant(TaskVariant):
    """User-supplied point prompts - clicks on the image to indicate objects.

    `inputs.points` is a list of {x, y, label} with x,y in [0,1] (normalized
    to the image) and label=1 (include/foreground) or 0 (exclude/background).
    We bypass the MaskGenerationPipeline (which only does auto-grid) and drive
    the underlying SAM model + processor directly. SAM returns 3 candidate
    masks per prompt; we keep the best-scoring one per point.

    Confirmed compatible: SAM v1 (`sam`), SAM 2 / 2.1 (`sam2`, `sam2_video`
    single-image mode), SAM 3 base (`sam3`). Not supported here: text-prompted
    (`sam3_lite_text`) or video/tracker (`*_video`, `sam3_tracker`) - they
    expect a different input modality than a point list."""
    name = "point-prompt"

    _INCOMPATIBLE_MODEL_TYPES = {
        "sam3_lite_text",
        "sam3_tracker",
    }

    def can_handle(self, info, inputs):
        pts = inputs.get("points")
        if not (isinstance(pts, list) and len(pts) > 0 and inputs.get("dataUrl")):
            return False
        mt = str(info.get("model_type") or "").lower()
        if mt in self._INCOMPATIBLE_MODEL_TYPES:
            return False
        return True

    def run(self, state, inputs, params):
        import numpy as np
        import torch
        from PIL import Image

        img = decode_image(inputs["dataUrl"])
        W, H = img.size

        model = state.model or getattr(state.pipe, "model", None)
        processor = (state.processor
                     or getattr(state.pipe, "image_processor", None)
                     or getattr(state.pipe, "processor", None))
        if model is None or processor is None:
            raise ValueError("SAM model/processor unavailable for point-prompt mode")

        if not hasattr(processor, "image_processor"):
            try:
                from transformers import AutoProcessor
                processor = AutoProcessor.from_pretrained(state.info["model_id"])
            except Exception as e:
                raise ValueError(
                    f"Couldn't load wrapping SamProcessor for point prompts "
                    f"(model_type={info_model_type(state)!r}): {e}"
                )

        raw_pts = inputs["points"]
        coords = [[int(p.get("x", 0.0) * W), int(p.get("y", 0.0) * H)] for p in raw_pts]
        labels = [int(p.get("label", 1)) for p in raw_pts]

        try:
            proc_inputs = processor(
                img,
                input_points=[coords],
                input_labels=[labels],
                return_tensors="pt",
            )
        except TypeError as e:
            raise ValueError(
                f"This SAM variant's processor doesn't accept point prompts "
                f"(model_type={info_model_type(state)!r}): {e}"
            )
        dev = next(model.parameters()).device
        proc_inputs = {k: (v.to(dev) if hasattr(v, "to") else v) for k, v in proc_inputs.items()}

        with torch.no_grad():
            outputs = model(**proc_inputs)

        if not hasattr(outputs, "pred_masks"):
            raise ValueError(
                f"SAM output missing `pred_masks` (model_type={info_model_type(state)!r}). "
                "This variant may expect a different prompt shape - open an issue with the repo id."
            )
        post_process = (getattr(getattr(processor, "image_processor", None), "post_process_masks", None)
                        or getattr(processor, "post_process_masks", None))
        if post_process is None:
            raise ValueError("SAM processor exposes no post_process_masks - cannot rescale to original size")

        reshaped = proc_inputs.get("reshaped_input_sizes")
        if reshaped is None:
            reshaped = proc_inputs.get("reshaped_sizes")
        if reshaped is None:
            raise ValueError("SAM processor didn't return reshaped input sizes - can't post-process masks")

        masks_by_batch = post_process(
            outputs.pred_masks.cpu(),
            proc_inputs["original_sizes"].cpu(),
            reshaped.cpu() if hasattr(reshaped, "cpu") else reshaped,
        )
        iou_scores = outputs.iou_scores.cpu()

        per_point_masks = masks_by_batch[0]
        per_point_scores = iou_scores[0]

        alpha = int(params.get("overlay_alpha", 140))
        overlay_arr = np.zeros((H, W, 4), dtype=np.uint8)
        legend = []
        exported_masks = []
        total = max(1, W * H)

        for i in range(per_point_masks.shape[0]):
            best_j = int(torch.argmax(per_point_scores[i]).item())
            mask_tensor = per_point_masks[i, best_j]
            arr = mask_tensor.numpy().astype(bool) if hasattr(mask_tensor, "numpy") else np.asarray(mask_tensor).astype(bool)
            if arr.shape[:2] != (H, W):
                pil = Image.fromarray((arr.astype(np.uint8) * 255))
                pil = pil.resize((W, H), Image.NEAREST)
                arr = np.array(pil) > 127
            n = int(arr.sum())
            pct = 100.0 * n / total
            rgb = REGION_PALETTE[i % len(REGION_PALETTE)]
            overlay_arr[arr] = [rgb[0], rgb[1], rgb[2], alpha]
            if params.get("export_masks"):
                exported_masks.append({"label": f"region {len(exported_masks)+1}", "dataUrl": encode_png_data_url(Image.fromarray(arr.astype(np.uint8) * 255, mode="L"))})
            legend.append({
                "label": f"point {i + 1} ({'include' if labels[i] == 1 else 'exclude'})",
                "color": f"rgb({rgb[0]},{rgb[1]},{rgb[2]})",
                "coverage": round(pct, 1),
                "score": float(per_point_scores[i, best_j]),
            })

        overlay = Image.fromarray(overlay_arr, mode="RGBA")
        annotated = composite_masks(img, overlay)
        result = ok.masks(overlay, legend)
        if params.get("export_masks"):
            result["masks"] = exported_masks
        result["annotated"] = encode_png_data_url(annotated)
        return result

class MaskGenerationTask(TaskHandler):
    """SAM family - automatic grid-sampling mask generation by default, or
    point-prompted when the caller supplies `inputs.points`."""
    name = "mask-generation"
    output_kind = "masks"
    default_params = {
        "points_per_batch": 64,
        "min_mask_pct": 0.5,
        "overlay_alpha": 140,
        "max_masks": 64,
    }
    variants = [PointPromptVariant(), AutoMaskGenVariant()]

    def load_pipeline(self, info, device, extra_kwargs=None):
        """Try the standard pipeline() path first (works for SAM v1 and, in
        recent transformers, SAM 2). If that fails - usually because the
        installed transformers' AutoModelForMaskGeneration mapping doesn't
        cover the model_type (common for bleeding-edge SAM 3 checkpoints) -
        fall back to AutoModel + AutoProcessor. The point-prompt variant
        works on model+processor directly and is unaffected."""
        from transformers import pipeline as hf_pipeline
        from io_utils import pipeline_device_arg, resolve_device
        kwargs = dict(extra_kwargs or {})

        import torch
        on_mps = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
        device_arg = -1 if on_mps else pipeline_device_arg()

        try:
            pipe = hf_pipeline(self.runtime_task(), model=info["model_id"], device=device_arg, **kwargs)
            return LoadedPipeline(
                info=info, device=device, pipe=pipe,
                model=getattr(pipe, "model", None),
                processor=(getattr(pipe, "processor", None)
                           or getattr(pipe, "image_processor", None)),
            )
        except Exception as pipe_err:
            import sys
            print(f"[mask-generation] pipeline() failed for {info.get('model_id')!r}: "
                  f"{pipe_err}. Loading model + processor directly.", file=sys.stderr)
            try:
                from transformers import AutoModelForMaskGeneration, AutoProcessor
            except ImportError as ie:
                raise RuntimeError(
                    f"Couldn't load {info.get('model_id')!r}: {pipe_err}. "
                    f"AutoModelForMaskGeneration also unavailable ({ie}). "
                    f"This transformers version may not support this SAM variant - upgrade transformers."
                )
            model = AutoModelForMaskGeneration.from_pretrained(info["model_id"], **kwargs)
            processor = AutoProcessor.from_pretrained(info["model_id"], **kwargs)
            dev = torch.device("cpu") if on_mps else resolve_device()
            if dev is not False:
                model = model.to(dev)
            model.eval()
            return LoadedPipeline(info=info, device=device, pipe=None, model=model, processor=processor)
