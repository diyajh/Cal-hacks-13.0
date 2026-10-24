"""Product retrieval. Person 1 never builds raw Apify requests (contract §23).

Order of sources for each ProductSearchRequest:
  1. Disk cache of a previous identical LIVE search (avoids re-paying for Apify during testing/demos)
  2. Person 2's POST /products/search (PRODUCT_SEARCH_URL) -> Apify -> Google Shopping
  3. If the live service ERRORS/TIMES OUT: Person 2's fallback-data/products.json (cached real products)
  4. agents/mock_products.json ONLY if no live URL is configured or USE_MOCK_FALLBACK=true

A live search that succeeds but finds nothing returns [] (it does NOT silently switch to mock data).
Returns (products, source_label, stats) so agents report honestly where data came from.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from functools import lru_cache

from agents import config
from agents.core import taxonomy as tx
from agents.core.contract import normalize_product

log = logging.getLogger("agents.products")

SOURCE_LABELS = {
    "product_service": "live product service",
    "cache": "live product service (cached)",
    "person2_fallback": "Person 2 fallback file",
    "mock": "mock catalog",
    "none": "no source",
}


def make_search_request(query: str, category: str | None = None, colors: list[str] | None = None,
                        tags: list[str] | None = None, max_price: float | None = None, limit: int = 20) -> dict:
    return {"query": query, "category": category, "colors": colors or [], "tags": tags or [],
            "max_price": round(max_price, 2) if max_price is not None else None, "limit": limit}


# --------------------------------------------------------------------------- live service + cache

def _cache_path(req: dict):
    key = json.dumps({"url": config.PRODUCT_SEARCH_URL, "req": req}, sort_keys=True)
    return config.SEARCH_CACHE_DIR / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")


def _cache_get(req: dict) -> list | None:
    path = _cache_path(req)
    try:
        if path.exists() and time.time() - path.stat().st_mtime < config.SEARCH_CACHE_HOURS * 3600:
            return json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    return None


def _cache_put(req: dict, raw: list) -> None:
    try:
        config.SEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(req).write_text(json.dumps(raw))
    except OSError as exc:
        log.warning("could not cache search: %s", exc)


def clear_cache() -> int:
    n = 0
    if config.SEARCH_CACHE_DIR.exists():
        for f in config.SEARCH_CACHE_DIR.glob("*.json"):
            f.unlink()
            n += 1
    return n


def _fetch_live(req: dict) -> list:
    """Raw product dicts from Person 2. Raises on network/HTTP/format errors."""
    http_req = urllib.request.Request(
        config.PRODUCT_SEARCH_URL, data=json.dumps(req).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(http_req, timeout=config.PRODUCT_SEARCH_TIMEOUT) as resp:
        body = json.loads(resp.read().decode())
    raw = body if isinstance(body, list) else (body.get("products") if isinstance(body, dict) else None)
    if not isinstance(raw, list):
        raise ValueError(f"unexpected response shape: {type(body).__name__}")
    return raw


def _validate(raw: list, req: dict) -> tuple[list[dict], dict]:
    """Normalize + enforce hard filters ourselves (never trust upstream for budget/category)."""
    stats = {"received": len(raw), "invalid": 0, "unavailable": 0, "over_max_price": 0, "wrong_category": 0}
    samples = []  # first few rejected items with the reason, for debugging schema mismatches

    def reject(kind, item, why):
        stats[kind] += 1
        if len(samples) < 5 and isinstance(item, dict):
            samples.append({"id": item.get("id"), "name": str(item.get("name"))[:60], "category": item.get("category"),
                            "price": item.get("price"), "reason": why})

    out = []
    for item in raw:
        p = normalize_product(item)
        if p is None:
            missing = [k for k in ("id", "name", "price", "category") if not isinstance(item, dict) or item.get(k) in (None, "")]
            why = f"missing {', '.join(missing)}" if missing else f"unrecognised category or price: {item.get('category')!r}/{item.get('price')!r}"
            reject("invalid", item, why)
        elif not p["available"]:
            reject("unavailable", item, "available=false")
        elif req.get("max_price") is not None and p["price"] > req["max_price"]:
            reject("over_max_price", item, f"price {p['price']} > max {req['max_price']}")
        elif req.get("category") and p["category"] != req["category"]:
            reject("wrong_category", item, f"category {item.get('category')!r} != requested {req['category']!r}")
        else:
            out.append(p)
    stats["kept"] = len(out)
    if samples:
        stats["rejected_samples"] = samples
    return out, stats


# --------------------------------------------------------------------------- fallbacks

@lru_cache(maxsize=4)
def _load_file(path_str: str) -> tuple[dict, ...]:
    from pathlib import Path
    path = Path(path_str)
    if not path.exists():
        return tuple()
    try:
        raw = json.loads(path.read_text())
        raw = raw.get("products", raw) if isinstance(raw, dict) else raw
        return tuple(p for p in (normalize_product(x) for x in raw) if p)
    except (ValueError, OSError) as exc:
        log.warning("bad fallback file %s: %s", path, exc)
        return tuple()


def load_fallback_catalog() -> tuple[dict, ...]:
    """Mock catalog (used by tests/check tools)."""
    return _load_file(str(config.MOCK_PRODUCTS_FILE))


def _local_search(req: dict, catalog: tuple[dict, ...]) -> list[dict]:
    words = [w for w in tx.tokenize(req.get("query") or "") if w not in tx.STOPWORDS]
    out = []
    for p in catalog:
        if not p["available"]:
            continue
        if req.get("category") and p["category"] != req["category"]:
            continue
        if req.get("max_price") is not None and p["price"] > req["max_price"]:
            continue
        text = tx.product_text(p)
        relevance = sum(1 for w in words if tx.term_in_text(w, text))
        relevance += sum(1 for c in req.get("colors") or [] if c in p["colors"])
        relevance += sum(0.5 for t in req.get("tags") or [] if tx.term_in_text(t, text))
        out.append((relevance, -p["price"], p))
    out.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [p for _, _, p in out[: req.get("limit") or 20]]


def _fallback(req: dict, error: str | None) -> tuple[list[dict], str, dict]:
    stats = {"error": error} if error else {}
    p2 = _load_file(str(config.PERSON2_FALLBACK_FILE))
    if p2:
        return _local_search(req, p2), "person2_fallback", stats
    if config.USE_MOCK_FALLBACK:
        return _local_search(req, load_fallback_catalog()), "mock", stats
    return [], "none", stats


# --------------------------------------------------------------------------- entry point

# Circuit breaker: after a failure, skip the live service briefly instead of waiting on it again and again.
_DOWN = {"until": 0.0, "reason": ""}
BREAKER_SECONDS = 30


def search_products(req: dict) -> tuple[list[dict], str, dict]:
    if not config.PRODUCT_SEARCH_URL:
        return _fallback(req, None)
    cached = _cache_get(req)
    if cached is not None:
        products, stats = _validate(cached, req)
        return products, "cache", stats
    if time.time() < _DOWN["until"]:
        return _fallback(req, f"product service unavailable ({_DOWN['reason']})")
    try:
        raw = _fetch_live(req)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        detail = getattr(exc, "reason", None) or str(exc)
        if isinstance(exc, urllib.error.HTTPError):
            detail = f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:200]}"
        log.warning("product service failed for %r: %s", req.get("query"), detail)
        _DOWN.update(until=time.time() + BREAKER_SECONDS, reason=str(detail)[:80])
        return _fallback(req, str(detail))
    _cache_put(req, raw)
    products, stats = _validate(raw, req)
    return products, "product_service", stats
