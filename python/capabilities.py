"""Shared workspace/MCP parameter definitions. Discovery never loads weights."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

PARAMETERS = json.loads(Path(__file__).with_name("task_parameters.json").read_text(encoding="utf-8"))


def validate_params(task, params):
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    schema = {p["key"]: p for p in PARAMETERS.get(task, [])}
    for key, value in params.items():
        if key not in schema:
            raise ValueError(f"Unsupported parameter {key!r} for {task}")
        rule = schema[key]
        kind = rule["type"]
        if kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be boolean")
        elif kind in ("number", "range"):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{key} must be a finite number")
            if ("min" in rule and value < rule["min"]) or ("max" in rule and value > rule["max"]):
                raise ValueError(f"{key} must be between {rule.get('min')} and {rule.get('max')}")
            if kind == "number" and rule.get("step", 1) >= 1 and int(value) != value:
                raise ValueError(f"{key} must be an integer")
        elif kind == "select":
            if value not in [o["value"] for o in rule["options"]]:
                raise ValueError(f"Unsupported {key}: {value}")
        elif not isinstance(value, str):
            raise ValueError(f"{key} must be text")
    return dict(params)


def model_capabilities(model_id):
    from routing import inspect_model, pick_adapter
    from services.store_service import list_installed
    from runtime import engine, probe_status
    from tasks import get_task
    info = inspect_model(model_id)
    installed = list_installed()
    task = info.get("pipeline_tag") or installed.get(model_id, {}).get("task")
    info["pipeline_tag"] = task
    handler = get_task(task)
    supported, error = True, None
    try:
        adapter = pick_adapter(info)
        adapter_name = type(adapter).__name__
    except Exception as exc:
        supported, error, adapter_name = False, str(exc), None
    image_tasks = {"image-to-text", "image-text-to-text", "document-question-answering", "depth-estimation", "image-classification", "zero-shot-image-classification", "object-detection", "zero-shot-object-detection", "image-segmentation", "mask-generation", "image-to-image", "inpainting"}
    input_types = ["image", "text"] if task in image_tasks else ["audio"] if task == "automatic-speech-recognition" else ["text"]
    output = handler.output_kind if handler else "image" if task in ("text-to-image", "image-to-image", "inpainting") else None
    output_types = {"boxes": ["image", "structured"], "masks": ["image", "structured"],
                    "labels": ["structured"], "vector": ["structured"]}.get(output, [output] if output else [])
    parameters = [dict(p) for p in PARAMETERS.get(task, [])]
    for p in parameters:
        p["available"] = not p.get("model_pattern") or bool(re.search(p["model_pattern"], model_id, re.I))
        if supported:
            defaults = {"num_inference_steps": getattr(adapter, "DEFAULT_STEPS", None),
                        "guidance_scale": getattr(adapter, "DEFAULT_GUIDANCE", None)}
            value = (getattr(adapter, "override", {}).get("params") or {}).get(p["key"], defaults.get(p["key"]))
            if value is not None:
                p["default"] = value
    return {"model": model_id, "task": task, "supported": supported, "error": error,
            "adapter": adapter_name, "input_types": input_types, "output_types": output_types, "output_kind": output,
            "parameters": parameters, "installed": model_id in installed,
            "loaded": model_id in engine().loaded_model_ids(), "runtime": probe_status(),
            "voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"] if "speecht5" in model_id.lower() else [],
            "limits": {"images_per_request": 1, "languages": "model-dependent", "hardware_fit": "Not measured; architecture support does not guarantee sufficient memory."}}
