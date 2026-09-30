"""Diffusers fallback. text-to-image, img2img, inpainting."""
from __future__ import annotations

from .base import Adapter
import output_kinds as ok
from io_utils import decode_image, resolve_device, torch_dtype_for_device

class DiffusersAdapter(Adapter):
    @classmethod
    def can_handle(cls, info):
        if info.get("library") == "diffusers":
            return info.get("pipeline_tag") != "text-to-video"
        tag = info.get("pipeline_tag")
        return tag in ("text-to-image", "image-to-image", "inpainting")

    def load(self, info, device):
        self.info = info
        self.device = device
        self.task = info.get("pipeline_tag") or "text-to-image"
        dtype = torch_dtype_for_device()

        from diffusers import (
            AutoPipelineForText2Image,
            AutoPipelineForImage2Image,
            AutoPipelineForInpainting,
        )
        cls = {
            "image-to-image": AutoPipelineForImage2Image,
            "inpainting":     AutoPipelineForInpainting,
        }.get(self.task, AutoPipelineForText2Image)

        kwargs = {"torch_dtype": dtype}
        if self.override.get("trust_remote_code"):
            kwargs["trust_remote_code"] = True
        self.pipe = cls.from_pretrained(info["model_id"], **kwargs)
        resolved = resolve_device()
        if resolved is not False:
            self.pipe = self.pipe.to(resolved)

    def run(self, inputs, params):
        prompt = (inputs.get("text") or "").strip()
        if not prompt:
            raise ValueError("Prompt required")
        kwargs = {k: params[k] for k in
                  ("num_inference_steps", "guidance_scale", "negative_prompt", "strength",
                   "width", "height")
                  if k in params}
        kwargs.setdefault("num_inference_steps", 20)
        kwargs.setdefault("guidance_scale", 7.5)
        if params.get("seed") is not None:
            import torch
            kwargs["generator"] = torch.Generator(device="cpu").manual_seed(int(params["seed"]))

        if self.task == "image-to-image" and inputs.get("dataUrl"):
            kwargs["image"] = decode_image(inputs["dataUrl"])
        elif self.task == "inpainting" and inputs.get("dataUrl"):
            kwargs["image"] = decode_image(inputs["dataUrl"])
            if not inputs.get("maskDataUrl"):
                raise ValueError("Inpainting requires maskDataUrl (white pixels are replaced)")
            kwargs["mask_image"] = decode_image(inputs["maskDataUrl"]).convert("L")
        if self.task in ("image-to-image", "inpainting") and "image" not in kwargs:
            raise ValueError("This task requires an input image")

        # Supported diffusers pipelines check cancellation between denoising steps.
        import inspect
        if "callback_on_step_end" in inspect.signature(self.pipe.__call__).parameters:
            def step_end(pipe, step, timestep, callback_kwargs):
                from runtime import stop_requested
                if params.get("_progress"):
                    params["_progress"](step + 1, kwargs["num_inference_steps"])
                if stop_requested():
                    raise RuntimeError("Inference cancelled")
                return callback_kwargs
            kwargs["callback_on_step_end"] = step_end

        result = self.pipe(prompt, **kwargs)
        image = result.images[0]
        return ok.image(image)
