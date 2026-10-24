"""Product retrieval. Person 1 never builds raw Apify requests (contract §23).

1. POST ProductSearchRequest to Person 2's /products/search (PRODUCT_SEARCH_URL).
2. On error / timeout / empty / unusable -> local fallback catalog (same Product schema).
Returns (products, source_label) so agents can report honestly where data came from.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from functools import lru_cache

from agents import config
from agents.core import taxonomy as tx
from agents.core.contract import normalize_product

log = logging.getLogger("agents.products")


def make_search_request(query: str, category: str | None = None, colors: list[str] | None = None,
                        tags: list[str] | None = None, max_price: float | None = None, limit: int = 20) -> dict:
    return {"query": query, "category": category, "colors": colors or [], "tags": tags or [],
            "max_price": round(max_price, 2) if max_price is not None else None, "limit": limit}


def _remote_search(req: dict) -> list[dict] | None:
    if not config.PRODUCT_SEARCH_URL:
        return None
    try:
        http_req = urllib.request.Request(
            config.PRODUCT_SEARCH_URL, data=json.dumps(req).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(http_req, timeout=config.PRODUCT_SEARCH_TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        log.warning("product service failed: %s", exc)
        return None
    raw = body if isinstance(body, list) else (body.get("products") if isinstance(body, dict) else None)
    if not isinstance(raw, list):
        return None
    products = [p for p in (normalize_product(x) for x in raw) if p]
    return products or None


@lru_cache(maxsize=1)
def load_fallback_catalog() -> tuple[dict, ...]:
    for path in config.FALLBACK_PRODUCT_FILES:
        if path.exists():
            try:
                raw = json.loads(path.read_text())
                raw = raw.get("products", raw) if isinstance(raw, dict) else raw
                products = [p for p in (normalize_product(x) for x in raw) if p]
                if products:
                    log.info("loaded %d fallback products from %s", len(products), path)
                    return tuple(products)
            except (ValueError, OSError) as exc:
                log.warning("bad fallback file %s: %s", path, exc)
    return tuple()


def _local_search(req: dict) -> list[dict]:
    words = [w for w in tx.tokenize(req.get("query") or "") if w not in tx.STOPWORDS]
    out = []
    for p in load_fallback_catalog():
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


def search_products(req: dict) -> tuple[list[dict], str]:
    remote = _remote_search(req)
    if remote is not None:
        # enforce max_price ourselves too: never trust upstream filtering for a hard constraint
        if req.get("max_price") is not None:
            remote = [p for p in remote if p["price"] <= req["max_price"]]
        if req.get("category"):
            remote = [p for p in remote if p["category"] == req["category"]]
        return remote, "product_service"
    return _local_search(req), "fallback_catalog"
