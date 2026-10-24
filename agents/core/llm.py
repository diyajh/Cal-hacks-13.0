"""Minimal stdlib LLM client that returns parsed JSON. Optional: if no key, returns None.

Supports OpenAI Chat Completions or Anthropic Messages via plain HTTPS (no SDK needed).
The LLM is ONLY used to understand language. It never supplies prices or product facts.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from agents import config

log = logging.getLogger("agents.llm")

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"        # override with LLM_MODEL
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"  # override with LLM_MODEL


def llm_available() -> bool:
    return bool(config.OPENAI_API_KEY or config.ANTHROPIC_API_KEY)


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


def call_llm_json(system: str, user: str) -> dict | None:
    """Returns a dict or None on any failure (caller falls back to rules)."""
    try:
        if config.OPENAI_API_KEY:
            data = _post(
                "https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {config.OPENAI_API_KEY}", "Content-Type": "application/json"},
                {
                    "model": config.LLM_MODEL or DEFAULT_OPENAI_MODEL,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                },
            )
            return _extract_json(data["choices"][0]["message"]["content"])
        if config.ANTHROPIC_API_KEY:
            data = _post(
                "https://api.anthropic.com/v1/messages",
                {"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
                {
                    "model": config.LLM_MODEL or DEFAULT_ANTHROPIC_MODEL,
                    "max_tokens": 1500,
                    "temperature": 0,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            return _extract_json(text)
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as exc:
        log.warning("LLM call failed: %s", exc)
    return None
