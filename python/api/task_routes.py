"""Typed task entry point shared by synchronous MCP calls and background jobs."""
from __future__ import annotations

import asyncio
import time
import uuid
from fastapi import APIRouter, Body, HTTPException
import runtime
from capabilities import model_capabilities, validate_params

router = APIRouter(prefix="/v1")
TASKS = {"image-to-text", "image-text-to-text", "document-question-answering", "image-classification", "zero-shot-image-classification", "depth-estimation", "image-to-image", "inpainting", "object-detection", "zero-shot-object-detection", "image-segmentation", "mask-generation", "text-to-image", "automatic-speech-recognition", "text-to-speech", "text-generation", "translation", "summarization"}


async def execute(payload, job=None):
    from api.routes import _media_run
    from routing import inspect_model
    task, model = payload.get("task"), payload.get("model")
    if task not in TASKS or not isinstance(model, str) or not model.strip():
        raise ValueError("A supported task and explicit model are required")
    inputs = payload.get("inputs", {})
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be an object")
    params = validate_params(task, payload.get("params", {}))
    for key in ("dataUrl", "maskDataUrl"):
        if key in inputs and (not isinstance(inputs[key], str) or not inputs[key].startswith("data:") or len(inputs[key]) > 90_000_000):
            raise ValueError(f"{key} must be a media data URL no larger than 64 MiB decoded")
    if inputs.get("points"):
        points = inputs["points"]
        if not isinstance(points, list) or len(points) > 256:
            raise ValueError("points must contain at most 256 entries")
        for p in points:
            if not isinstance(p, dict) or not all(isinstance(p.get(k), (int, float)) and 0 <= p[k] <= 1 for k in ("x", "y")) or p.get("label", 1) not in (0, 1):
                raise ValueError("Each point requires x/y in [0,1] and label 0 or 1")
    info = await runtime.run_blocking(inspect_model, model)
    actual = info.get("pipeline_tag")
    aliases = {"image-to-text", "image-text-to-text"}
    if actual and actual != task and not {actual, task} <= aliases:
        raise ValueError(f"Model task is {actual}, requested {task}. Choose a compatible model.")
    started = time.monotonic()
    mid, out = await _media_run(model, (task,), None, inputs, params, task_hint=task, job=job)
    return {"model": mid, "task": task, "parameters": params, "elapsed_seconds": round(time.monotonic() - started, 3), "output": out}


@router.get("/models/capabilities")
async def capabilities(model: str):
    return await runtime.run_blocking(model_capabilities, model)


@router.post("/tasks/run")
async def run_task(payload: dict = Body(...)):
    from api.routes import _media_err
    try:
        return await execute(payload)
    except Exception as exc:
        return _media_err(exc)


# Jobs belong to this API process; completed records are bounded to 100.
JOBS = {}


def public_job(job):
    return {k: v for k, v in job.items() if not k.startswith("_")}


@router.post("/jobs")
async def start_job(payload: dict = Body(...)):
    if len([j for j in JOBS.values() if j["status"] in ("queued", "running", "cancelling")]) >= 16:
        raise HTTPException(429, "The job queue is full")
    for key in list(JOBS):
        if len(JOBS) < 100:
            break
        if JOBS[key]["status"] in ("completed", "failed", "cancelled"):
            del JOBS[key]
    jid = uuid.uuid4().hex
    job = {"id": jid, "status": "queued", "created_at": time.time(), "cancel_requested": False,
           "progress": {"stage": "waiting", "completed": 0, "total": None}}
    JOBS[jid] = job

    async def work():
        try:
            result = await execute(payload, job)
            job.update(status="cancelled" if job["cancel_requested"] else "completed")
            if not job["cancel_requested"]:
                job["result"] = result
                job["progress"] = {"stage": "completed", "completed": 1, "total": 1}
        except asyncio.CancelledError:
            job["status"] = "cancelled"
        except Exception as exc:
            job.update(status="cancelled" if job["cancel_requested"] else "failed", error=str(exc))
        finally:
            job["finished_at"] = time.time()
    job["_task"] = asyncio.create_task(work())
    return public_job(job)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job")
    return public_job(JOBS[job_id])


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    await get_job(job_id)
    job = JOBS[job_id]
    if job["status"] == "queued":
        job["cancel_requested"] = True
        job["_task"].cancel()
        job["status"] = "cancelled"
    elif job["status"] == "running":
        job.update(cancel_requested=True, status="cancelling")
        # Only running jobs own the shared lock. Never interrupt unrelated UI work.
        runtime.request_stop()
    return public_job(job)
