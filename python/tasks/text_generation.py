"""text-generation / translation / summarization - variants: plain, chat-template, reasoning-think-parse.

Note on seq2seq tasks: recent transformers removed `text2text-generation`,
`summarization`, and `translation` from the public pipeline registry. Those
three tasks now bypass `transformers.pipeline()` and load the model directly
via `AutoModelForSeq2SeqLM` + tokenizer (see _Seq2SeqLMTask below).

The T5 / BART / Pegasus model families are intentionally not surfaced in
`supported_architectures.json`. The seq2seq path here remains for Marian /
NLLB / M2M-100 / FSMT (translation) and Prophetnet (summarization)."""
from __future__ import annotations
import re

from .base import TaskHandler, TaskVariant, LoadedPipeline
import output_kinds as ok

def _conversation(inputs):
    messages = inputs.get("messages")
    if isinstance(messages, list):
        valid = [dict(role=m["role"], content=m["content"]) for m in messages
                 if isinstance(m, dict) and m.get("role") in ("system", "user", "assistant")
                 and isinstance(m.get("content"), str)]
        if valid:
            return valid
    return [{"role": "user", "content": inputs["text"].strip()}]


def _chat_prompt(state, inputs):
    messages = _conversation(inputs)
    try:
        return state.pipe.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        if len(messages) == 1:
            return messages[0]["content"]
        return "\n\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\n\nassistant:"


def _is_chat_model(info):
    arch = " ".join(info.get("architectures") or []).lower()
    tags = " ".join(info.get("tags") or []).lower()
    mid = (info.get("model_id") or "").lower()
    return any(k in tags for k in ("conversational", "chat")) or "instruct" in mid or "chat" in mid

def _is_reasoning_model(info):
    mid = (info.get("model_id") or "").lower()
    return "r1" in mid or "qwq" in mid or "reasoning" in mid

class ReasoningVariant(TaskVariant):
    """DeepSeek-R1, QwQ - strip <think>...</think> from the output."""
    name = "reasoning-think-parse"

    def can_handle(self, info, inputs):
        return (inputs.get("text") or "").strip() and _is_reasoning_model(info) and (_is_chat_model(info) or bool(inputs.get("messages")))

    def run(self, state, inputs, params):
        prompt = _chat_prompt(state, inputs)
        kwargs = {k: params[k] for k in ("max_new_tokens", "temperature", "top_p", "top_k", "do_sample") if k in params}
        kwargs.setdefault("max_new_tokens", 512)
        from generation_control import stopping_criteria
        kwargs["stopping_criteria"] = stopping_criteria()
        raw = state.pipe(prompt, **kwargs)
        out = (raw[0] if isinstance(raw, list) else raw).get("generated_text") or ""
        if out.startswith(prompt):
            out = out[len(prompt):].lstrip()
        answer = re.sub(r"<think>.*?</think>\s*", "", out, flags=re.DOTALL).strip()
        return ok.text(answer or out)

class ChatTemplateVariant(TaskVariant):
    """Instruct / chat models - use the tokenizer's chat template."""
    name = "chat-template"

    def can_handle(self, info, inputs):
        return bool((inputs.get("text") or "").strip()) and (_is_chat_model(info) or bool(inputs.get("messages")))

    def run(self, state, inputs, params):
        prompt = _chat_prompt(state, inputs)
        kwargs = {k: params[k] for k in ("max_new_tokens", "temperature", "top_p", "top_k", "do_sample") if k in params}
        kwargs.setdefault("max_new_tokens", 256)
        from generation_control import stopping_criteria
        kwargs["stopping_criteria"] = stopping_criteria()
        raw = state.pipe(prompt, **kwargs)
        r0 = raw[0] if isinstance(raw, list) else raw
        out = r0.get("generated_text") or ""
        if out.startswith(prompt):
            out = out[len(prompt):].lstrip()
        return ok.text(out)

class PlainGenVariant(TaskVariant):
    name = "plain"

    def can_handle(self, info, inputs):
        return bool((inputs.get("text") or "").strip())

    def run(self, state, inputs, params):
        text = inputs["text"].strip()
        kwargs = {k: params[k] for k in ("max_new_tokens", "temperature", "top_p", "top_k", "do_sample") if k in params}
        kwargs.setdefault("max_new_tokens", 256)
        for k in ("src_lang", "tgt_lang"):
            if params.get(k):
                kwargs[k] = params[k]
        from generation_control import stopping_criteria
        kwargs["stopping_criteria"] = stopping_criteria()
        raw = state.pipe(text, **kwargs)
        r0 = raw[0] if isinstance(raw, list) else raw
        out = r0.get("generated_text") or r0.get("translation_text") or r0.get("summary_text") or ""
        if isinstance(out, str) and out.startswith(text):
            out = out[len(text):].lstrip()
        return ok.text(out)

class TextGenerationTask(TaskHandler):
    name = "text-generation"
    output_kind = "text"
    default_params = {"max_new_tokens": 256}
    variants = [ReasoningVariant(), ChatTemplateVariant(), PlainGenVariant()]

class Seq2SeqVariant(TaskVariant):
    """Encoder-decoder generation for Marian / NLLB / M2M-100 / FSMT / Prophetnet.
    Bypasses transformers.pipeline (which dropped these task names in recent
    versions) and calls model.generate() directly on the tokenized input."""
    name = "seq2seq-direct"

    def can_handle(self, info, inputs):
        return bool((inputs.get("text") or "").strip())

    def run(self, state, inputs, params):
        import torch
        text = inputs["text"].strip()
        tokenizer = state.processor
        model = state.model
        kwargs = {k: params[k] for k in ("max_new_tokens", "temperature", "top_p", "top_k", "do_sample") if k in params}
        kwargs.setdefault("max_new_tokens", 256)
        tok_kwargs = {}
        for k in ("src_lang", "tgt_lang"):
            if params.get(k):
                tok_kwargs[k] = params[k]
        if tok_kwargs:
            try:
                if "src_lang" in tok_kwargs:
                    tokenizer.src_lang = tok_kwargs["src_lang"]
                if "tgt_lang" in tok_kwargs and hasattr(tokenizer, "convert_tokens_to_ids"):
                    forced_bos = tokenizer.convert_tokens_to_ids(tok_kwargs["tgt_lang"])
                    if isinstance(forced_bos, int) and forced_bos > 0:
                        kwargs["forced_bos_token_id"] = forced_bos
            except Exception:
                pass
        device = next(model.parameters()).device
        ids = tokenizer(text, return_tensors="pt", truncation=True).input_ids.to(device)
        from generation_control import stopping_criteria
        kwargs["stopping_criteria"] = stopping_criteria()
        with torch.no_grad():
            out_ids = model.generate(ids, **kwargs)
        out = tokenizer.decode(out_ids[0], skip_special_tokens=True)
        return ok.text(out)

class _Seq2SeqLMTask(TaskHandler):
    """Shared loader for the three encoder-decoder pipeline tasks.
    Concrete subclasses just set `name`."""
    output_kind = "text"
    default_params = {"max_new_tokens": 256}
    variants = [Seq2SeqVariant()]

    def load_pipeline(self, info, device, extra_kwargs=None):
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        from io_utils import resolve_device, torch_dtype_for_device
        tokenizer = AutoTokenizer.from_pretrained(info["model_id"])
        model = AutoModelForSeq2SeqLM.from_pretrained(
            info["model_id"], torch_dtype=torch_dtype_for_device()
        )
        dev = resolve_device()
        if dev is not False:
            model = model.to(dev)
        model.eval()
        return LoadedPipeline(info=info, device=device, pipe=None, model=model, processor=tokenizer)

class TranslationTask(_Seq2SeqLMTask):
    name = "translation"

class SummarizationTask(_Seq2SeqLMTask):
    name = "summarization"
