"""image-segmentation - variants: semantic, instance, panoptic (all compose an overlay)."""
from __future__ import annotations

from .base import TaskHandler, TaskVariant
from ._render import composite_masks, encode_png_data_url
from io_utils import decode_image
import output_kinds as ok

CITYSCAPES_PALETTE = {
    "road":          (128, 64, 128),  "sidewalk":    (244, 35, 232),
    "building":      (70, 70, 70),    "wall":        (102, 102, 156),
    "fence":         (190, 153, 153), "pole":        (153, 153, 153),
    "traffic light": (250, 170, 30),  "traffic sign":(220, 220, 0),
    "vegetation":    (107, 142, 35),  "terrain":     (152, 251, 152),
    "sky":           (70, 130, 180),  "person":      (220, 20, 60),
    "rider":         (255, 0, 0),     "car":         (0, 0, 142),
    "truck":         (0, 0, 70),      "bus":         (0, 60, 100),
    "train":         (0, 80, 100),    "motorcycle":  (0, 0, 230),
    "bicycle":       (119, 11, 32),
}

FALLBACK_PALETTE = [
    (255, 99, 71),  (30, 144, 255), (50, 205, 50),  (255, 215, 0),
    (186, 85, 211), (0, 206, 209),  (255, 140, 0),  (220, 20, 60),
    (46, 139, 87), (138, 43, 226),  (0, 191, 255),  (255, 105, 180),
    (124, 252, 0), (255, 69, 0),    (0, 250, 154),  (255, 20, 147),
]

def _color_for(label: str, chosen: dict) -> tuple:
    if label in chosen:
        return chosen[label]
    canon = CITYSCAPES_PALETTE.get(label.lower().strip())
    chosen[label] = canon if canon is not None else FALLBACK_PALETTE[len(chosen) % len(FALLBACK_PALETTE)]
    return chosen[label]

def _build_overlay(img, results, params):
    """Shared overlay composition - covers semantic, instance, panoptic equally
    well as long as each result has a `mask` PIL image."""
    import numpy as np
    from PIL import Image
    W, H = img.size
    alpha = int(params.get("overlay_alpha", 140))
    min_pct = float(params.get("legend_min_pct", 0.3))
    overlay_arr = np.zeros((H, W, 4), dtype=np.uint8)
    chosen_colors: dict = {}
    per_label: dict = {}
    total = max(1, W * H)

    for i, r in enumerate(results):
        label = r.get("label") or f"class {i+1}"
        score = r.get("score")
        rgb = _color_for(label, chosen_colors)
        mask_img = r.get("mask")
        pct = 0.0
        if mask_img is not None:
            if mask_img.size != (W, H):
                mask_img = mask_img.resize((W, H), Image.NEAREST)
            positive = np.array(mask_img) > 127
            n = int(positive.sum())
            if n > 0:
                overlay_arr[positive] = [rgb[0], rgb[1], rgb[2], alpha]
            pct = 100.0 * n / total
        agg = per_label.setdefault(label, {"rgb": rgb, "score": score, "pct": 0.0})
        agg["pct"] += pct
        if score is not None and agg["score"] is None:
            agg["score"] = score

    legend = []
    for label, agg in sorted(per_label.items(), key=lambda kv: -kv[1]["pct"]):
        if agg["pct"] < min_pct:
            continue
        rgb = agg["rgb"]
        legend.append({
            "label": label,
            "color": f"rgb({rgb[0]},{rgb[1]},{rgb[2]})",
            "coverage": round(agg["pct"], 1),
            "score": float(agg["score"]) if agg["score"] is not None else None,
        })
    return Image.fromarray(overlay_arr, mode="RGBA"), legend

class SegmentationVariant(TaskVariant):
    """Works for semantic (Segformer/MaskFormer), instance (Mask2Former) and
    panoptic (DETR-panoptic) - the HF pipeline returns a uniform `list[{label,
    score, mask}]` shape for all three."""
    name = "pipeline-masks"

    def can_handle(self, info, inputs):
        return bool(inputs.get("dataUrl"))

    def run(self, state, inputs, params):
        img = decode_image(inputs["dataUrl"])
        results = state.pipe(img) or []
        overlay, legend = _build_overlay(img, results, params)
        annotated = composite_masks(img, overlay)
        result = ok.masks(overlay, legend)
        if params.get("export_masks"):
            result["masks"] = [{"label": r.get("label"), "score": r.get("score"),
                                "dataUrl": encode_png_data_url(r["mask"].convert("L"))}
                               for r in results if r.get("mask") is not None]
        result["annotated"] = encode_png_data_url(annotated)
        return result

class OneFormerVariant(TaskVariant):
    """OneFormer ships one set of weights for all three segmentation tasks
    (semantic / instance / panoptic). The HF `image-segmentation` pipeline
    doesn't expose the `task_inputs` arg, so this variant bypasses the
    pipeline and calls `model + processor` directly. Each mode uses a
    different post-processor.

    Dataset (label vocabulary) is fixed by the checkpoint id, e.g.
      shi-labs/oneformer_coco_swin_large       → COCO labels
      shi-labs/oneformer_ade20k_swin_large     → ADE20K labels
      shi-labs/oneformer_cityscapes_swin_large → Cityscapes labels
    """
    name = "oneformer"

    _processor_cache: dict = {}

    def can_handle(self, info, inputs):
        if not inputs.get("dataUrl"):
            return False
        return "oneformer" in (info.get("model_id") or "").lower()

    def _get_processor(self, model_id):
        cached = self._processor_cache.get(model_id)
        if cached is not None:
            return cached
        from transformers import OneFormerProcessor
        proc = OneFormerProcessor.from_pretrained(model_id)
        self._processor_cache[model_id] = proc
        return proc

    def _label_for(self, id2label, idx):
        if isinstance(id2label, dict):
            return id2label.get(idx) or id2label.get(str(idx)) or f"class {idx}"
        if isinstance(id2label, (list, tuple)) and 0 <= idx < len(id2label):
            return id2label[idx]
        return f"class {idx}"

    def run(self, state, inputs, params):
        import torch
        import numpy as np
        from PIL import Image
        from io_utils import resolve_device

        img = decode_image(inputs["dataUrl"])
        mode = (params.get("oneformer_mode") or "semantic").strip().lower()
        if mode not in ("semantic", "instance", "panoptic"):
            mode = "semantic"

        processor = self._get_processor(state.info["model_id"])
        model = state.model
        device = resolve_device()

        encoded = processor(images=[img], task_inputs=[mode], return_tensors="pt")
        if device is not False:
            encoded = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in encoded.items()}

        with torch.no_grad():
            outputs = model(**encoded)

        target_sizes = [(img.height, img.width)]
        id2label = getattr(model.config, "id2label", {}) or {}
        results = []

        if mode == "semantic":
            seg_maps = processor.post_process_semantic_segmentation(outputs, target_sizes=target_sizes)
            seg_arr = seg_maps[0].cpu().numpy()
            for cid in sorted(int(x) for x in np.unique(seg_arr)):
                if cid < 0:
                    continue
                mask = ((seg_arr == cid).astype("uint8")) * 255
                if int(mask.sum()) == 0:
                    continue
                results.append({
                    "label": str(self._label_for(id2label, cid)),
                    "score": None,
                    "mask": Image.fromarray(mask, mode="L"),
                })
        else:
            post = (processor.post_process_instance_segmentation if mode == "instance"
                    else processor.post_process_panoptic_segmentation)
            processed_out = post(outputs, target_sizes=target_sizes)
            res = processed_out[0] if isinstance(processed_out, list) else processed_out
            seg_arr = res["segmentation"].cpu().numpy()
            for seg_info in (res.get("segments_info") or []):
                sid = int(seg_info["id"])
                lid = int(seg_info["label_id"])
                score = seg_info.get("score")
                mask = ((seg_arr == sid).astype("uint8")) * 255
                if int(mask.sum()) == 0:
                    continue
                results.append({
                    "label": str(self._label_for(id2label, lid)),
                    "score": float(score) if score is not None else None,
                    "mask": Image.fromarray(mask, mode="L"),
                })

        overlay, legend = _build_overlay(img, results, params)
        annotated = composite_masks(img, overlay)
        result = ok.masks(overlay, legend)
        if params.get("export_masks"):
            result["masks"] = [{"label": r.get("label"), "score": r.get("score"),
                                "dataUrl": encode_png_data_url(r["mask"].convert("L"))}
                               for r in results if r.get("mask") is not None]
        result["annotated"] = encode_png_data_url(annotated)
        return result

class ImageSegmentationTask(TaskHandler):
    name = "image-segmentation"
    output_kind = "masks"
    default_params = {"overlay_alpha": 140, "legend_min_pct": 0.3}
    variants = [OneFormerVariant(), SegmentationVariant()]
