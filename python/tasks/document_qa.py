"""document-question-answering - Donut, LayoutLM, LayoutLMv3 and friends.

Two real shapes of model live under this pipeline tag:

  1. LayoutLM-style - needs a question. Internally OCRs the page (via a
     bundled tesseract or a precomputed words/boxes pair), feeds tokens to
     the model, returns extractive `[{answer, score, start, end}]`.
  2. Donut DocVQA - generative. Same pipeline accepts (image, question) and
     returns the same shape, but answers are free-form.

The image-to-text pipeline already handles pure OCR captioners (TrOCR, vanilla
Donut), so this task is specifically the question-answering shape."""
from __future__ import annotations

from .base import TaskHandler, TaskVariant
from io_utils import decode_image
import output_kinds as ok

class DocumentQAVariant(TaskVariant):
    name = "standard"

    def can_handle(self, info, inputs):
        return bool(inputs.get("dataUrl"))

    def run(self, state, inputs, params):
        img = decode_image(inputs["dataUrl"])
        question = (inputs.get("text") or "").strip()
        if not question:
            question = "What is the text content of this document?"

        kwargs = {}
        top_k = int(params.get("top_k", 1))
        if top_k > 1:
            kwargs["top_k"] = top_k

        result = state.pipe(image=img, question=question, **kwargs)

        answers = result if isinstance(result, list) else [result] if isinstance(result, dict) else []
        structured = [{k: r[k] for k in ("answer", "score", "start", "end") if k in r} for r in answers]
        def answer(text):
            return {**ok.text(text), "answers": structured}

        if isinstance(result, dict):
            return answer(result.get("answer") or "")
        if isinstance(result, list) and result:
            if top_k > 1:
                lines = []
                for r in result:
                    a = (r.get("answer") or "").strip()
                    if not a:
                        continue
                    s = r.get("score")
                    lines.append(f"{a}    ({s:.2f})" if isinstance(s, (int, float)) else a)
                return answer("\n".join(lines))
            top = result[0]
            return answer(top.get("answer") or "")
        return answer("")

class DocumentQATask(TaskHandler):
    name = "document-question-answering"
    output_kind = "text"
    default_params = {"top_k": 1}
    variants = [DocumentQAVariant()]
