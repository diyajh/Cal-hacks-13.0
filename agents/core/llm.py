"""Minimal stdlib LLM client that returns parsed JSON. Optional: if no key, returns None.

Supports Anthropic Messages or OpenAI Chat Completions via plain HTTPS (no SDK needed).
The LLM is ONLY used to understand language. It never supplies prices or product facts.
If the configured/default model isn't available on the key, the next candidate is tried.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from agents import config

log = logging.getLogger("agents.llm")

# Tried in order unless LLM_MODEL is set. Override with LLM_MODEL if your key uses another model.
ANTHROPIC_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"]
OPENAI_MODELS = ["gpt-4.1-mini", "gpt-4o-mini"]

LAST = {"provider": None, "model": None, "error": None}  # for diagnostics (agents.check llm)


def llm_available() -> bool:
    return bool(config.ANTHROPIC_API_KEY or config.OPENAI_API_KEY)


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?|```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                return None
    return None


def _anthropic(model: str, system: str, user: str) -> dict | None:
    data = _post("https://api.anthropic.com/v1/messages",
                 {"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                  "content-type": "application/json"},
                 {"model": model, "max_tokens": 1500, "temperature": 0, "system": system,
                  "messages": [{"role": "user", "content": user}]})
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return _extract_json(text)


def _openai(model: str, system: str, user: str) -> dict | None:
    data = _post("https://api.openai.com/v1/chat/completions",
                 {"Authorization": f"Bearer {config.OPENAI_API_KEY}", "Content-Type": "application/json"},
                 {"model": model, "temperature": 0, "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    return _extract_json(data["choices"][0]["message"]["content"])


def call_llm_json(system: str, user: str) -> dict | None:
    """Returns a dict or None on any failure (caller falls back to rules). Details in LAST."""
    if config.ANTHROPIC_API_KEY:
        provider, fn, models = "anthropic", _anthropic, ANTHROPIC_MODELS
    elif config.OPENAI_API_KEY:
        provider, fn, models = "openai", _openai, OPENAI_MODELS
    else:
        LAST.update(provider=None, model=None, error="no API key configured")
        return None
    if config.LLM_MODEL:
        models = [config.LLM_MODEL]
    for model in models:
        LAST.update(provider=provider, model=model, error=None)
        try:
            out = fn(model, system, user)
            if out is None:
                LAST["error"] = "model replied but not with valid JSON"
            return out
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            LAST["error"] = f"HTTP {exc.code}: {body}"
            log.warning("LLM %s/%s failed: %s", provider, model, LAST["error"])
            model_missing = exc.code == 404 or "model" in body.lower() and exc.code == 400
            if not model_missing:
                return None  # bad key / quota etc.: trying other models won't help
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as exc:
            LAST["error"] = str(exc)
            log.warning("LLM %s/%s failed: %s", provider, model, exc)
            return None
    return None
