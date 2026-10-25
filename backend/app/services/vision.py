"""Server-side wardrobe image analysis.

The vision model is restricted to visual attributes. It never supplies prices,
URLs, budgets, or purchase decisions. Those remain deterministic application data.
"""
from __future__ import annotations

import base64
import json
import os
import re
import uuid
from typing import Any

import httpx


class VisionNotConfiguredError(RuntimeError):
    pass


class VisionAnalysisError(RuntimeError):
    pass


ALLOWED_CATEGORIES = {
    "shirt", "top", "blouse", "button-up", "t-shirt", "sweater", "jacket",
    "overshirt", "coat", "outerwear", "dress", "skirt", "pants", "jeans",
    "shorts", "shoes", "sneakers", "boots", "bag", "accessory", "other",
}

FOOTWEAR_SUBTYPE_TERMS = {
    "sneaker": {"sneaker", "sneakers", "trainer", "trainers", "running", "runner", "athletic", "court", "tennis"},
    "sandal": {"sandal", "sandals", "slide", "slides", "flip flop", "espadrille"},
    "boot": {"boot", "boots", "hiking", "combat"},
    "heel": {"heel", "heels", "pump", "pumps", "stiletto", "platform"},
}


def _footwear_subtype(raw: dict[str, Any], category: str) -> str:
    value = str(raw.get("subtype") or raw.get("subcategory") or "").strip().lower().replace("-", " ")
    vocabulary = " ".join(str(raw.get(key) or "") for key in ("category", "subcategory", "subtype", "style", "description")).lower()
    for subtype, terms in FOOTWEAR_SUBTYPE_TERMS.items():
        if value == subtype or value in terms or any(term in vocabulary for term in terms):
            return subtype
    return value or "unknown"


def _json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise VisionAnalysisError("Vision provider did not return JSON") from exc
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError as nested:
            raise VisionAnalysisError("Vision provider returned malformed JSON") from nested
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise VisionAnalysisError("Vision response must contain an items array")
    return value


def normalize_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate and normalize the strict wardrobe response contract."""
    items: list[dict[str, Any]] = []
    for raw in payload.get("items", []):
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "other").strip().lower()
        confidence = raw.get("confidence", 0)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0
        normalized_category = category if category in ALLOWED_CATEGORIES else "other"
        normalized_subtype = _footwear_subtype(raw, normalized_category) if normalized_category in {"shoes", "sneakers", "boots"} else str(raw.get("subcategory") or "unknown").strip().lower()
        color = str(raw.get("color") or "unknown").strip().lower()
        name = str(raw.get("name") or " ".join(part for part in (color, normalized_subtype or normalized_category) if part)).strip()
        items.append({
            "id": str(raw.get("id") or f"vision_{uuid.uuid4().hex[:10]}"),
            "name": name,
            "category": normalized_category,
            "subcategory": normalized_subtype,
            "subtype": normalized_subtype,
            "color": color,
            "pattern": str(raw.get("pattern") or "unknown").strip().lower(),
            "material": str(raw.get("material") or "unknown").strip().lower(),
            "style": str(raw.get("style") or "unknown").strip().lower(),
            "formality": str(raw.get("formality") or "unknown").strip().lower(),
            "fit": str(raw.get("fit") or "unknown").strip().lower(),
            "confidence": round(confidence, 2),
        })
    return items


def _anthropic(image: bytes, content_type: str, model: str) -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    body = {
        "model": model,
        "max_tokens": 1200,
        "temperature": 0,
        "system": "Return only strict JSON matching the requested wardrobe schema.",
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": content_type,
                                             "data": base64.b64encode(image).decode()}},
            {"type": "text", "text": _PROMPT},
        ]}],
    }
    response = httpx.post("https://api.anthropic.com/v1/messages", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json",
    }, json=body, timeout=60)
    response.raise_for_status()
    return "".join(part.get("text", "") for part in response.json().get("content", [])
                   if part.get("type") == "text")


def _openai(image: bytes, content_type: str, model: str) -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    data_url = f"data:{content_type};base64,{base64.b64encode(image).decode()}"
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": _PROMPT}, {"role": "user", "content": [
            {"type": "text", "text": "Analyze every clearly visible clothing item in this wardrobe photo."},
            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
        ]}],
    }
    response = httpx.post("https://api.openai.com/v1/chat/completions", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
    }, json=body, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


_PROMPT = """Analyze the wardrobe image and return ONLY this JSON shape:
{"items":[{"category":"shoes","subcategory":"sneaker","subtype":"sneaker","color":"white","pattern":"solid","material":"unknown","style":"casual","formality":"casual","fit":"unisex","confidence":0.91}]}
Include one item per clearly visible garment/accessory. Do not infer hidden items. Use unknown when uncertain. Confidence is 0 to 1 for visual identification only. No markdown, commentary, prices, URLs, or recommendations."""


def analyze_wardrobe_image(image: bytes, content_type: str) -> list[dict[str, Any]]:
    if not image:
        raise VisionAnalysisError("The wardrobe image is empty")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not anthropic_key and not openai_key:
        raise VisionNotConfiguredError("Set OPENAI_API_KEY or ANTHROPIC_API_KEY in backend/.env")
    try:
        if anthropic_key:
            text = _anthropic(image, content_type, os.getenv("VISION_MODEL", "claude-3-5-sonnet-latest"))
        else:
            text = _openai(image, content_type, os.getenv("VISION_MODEL", "gpt-4o-mini"))
        return normalize_items(_json_object(text))
    except VisionAnalysisError:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise VisionAnalysisError(f"Vision provider request failed: {exc}") from exc
