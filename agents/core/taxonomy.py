"""Small hand-written fashion vocabulary. Deterministic and explainable to judges."""
from __future__ import annotations

import re

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "couple": 2, "few": 3,
}
ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "last": -1,
}

# garment noun -> slot category
GARMENTS = {
    "top": "top", "tops": "top", "tee": "top", "t-shirt": "top", "tshirt": "top", "shirt": "top",
    "blouse": "top", "tank": "top", "cami": "top", "camisole": "top", "bodysuit": "top",
    "sweater": "top", "crop top": "top", "halter": "top", "tube top": "top", "polo": "top",
    "skirt": "bottom", "skirts": "bottom", "shorts": "bottom", "pants": "bottom",
    "trousers": "bottom", "jeans": "bottom", "leggings": "bottom", "bottom": "bottom", "bottoms": "bottom",
    "dress": "dress", "sundress": "dress", "romper": "dress", "jumpsuit": "dress",
    "sneakers": "shoes", "sandals": "shoes", "heels": "shoes", "boots": "shoes", "shoes": "shoes",
    "flats": "shoes", "loafers": "shoes", "espadrilles": "shoes", "slides": "shoes", "mules": "shoes",
    "jacket": "outerwear", "blazer": "outerwear", "cardigan": "outerwear", "coat": "outerwear",
    "hat": "accessory", "bag": "accessory", "tote": "accessory", "sunglasses": "accessory",
    "belt": "accessory", "necklace": "accessory", "earrings": "accessory", "scarf": "accessory",
}
# words that only name a category (they do not narrow the subcategory)
GENERIC_CATEGORY_WORDS = {"top", "tops", "bottoms", "shoes", "outfit"}

DESCRIPTORS = {
    "crochet", "linen", "denim", "silk", "satin", "cotton", "knit", "lace", "leather", "suede",
    "maxi", "midi", "mini", "flowy", "wrap", "slip", "cropped", "crop", "oversized", "fitted",
    "wide-leg", "wide", "high-waisted", "strappy", "platform", "ribbed", "sheer", "floral",
    "striped", "button-down", "sleeveless", "straw", "woven",
}

COLORS = {
    "beige", "white", "cream", "ivory", "tan", "khaki", "sand", "oatmeal", "taupe", "camel",
    "brown", "black", "grey", "gray", "natural", "nude", "ecru", "stone", "navy", "blue",
    "light blue", "sky blue", "green", "sage", "olive", "red", "burgundy", "pink", "blush",
    "purple", "lavender", "yellow", "orange", "coral", "terracotta", "rust", "gold", "silver",
    "champagne", "neon", "neutral", "neutrals", "pastel", "pastels", "earth tones", "multicolor",
}
NEUTRALS = {
    "champagne", "beige", "white", "cream", "ivory", "tan", "khaki", "sand", "oatmeal", "taupe", "camel",
    "brown", "black", "grey", "gray", "natural", "nude", "ecru", "stone",
}
COLOR_GROUPS = {
    "neutral": NEUTRALS, "neutrals": NEUTRALS,
    "pastel": {"blush", "lavender", "light blue", "sky blue", "sage", "pink"},
    "earth tones": {"brown", "olive", "terracotta", "rust", "camel", "tan", "sage"},
    "neon": {"neon", "fluorescent", "lime", "hot pink", "highlighter", "electric"},
}

STYLES = {
    "beachy": ["beach", "beachy", "coastal", "boho", "summer", "resort", "linen", "crochet", "breezy"],
    "coastal": ["coastal", "beach", "nautical", "linen", "resort", "breezy", "summer"],
    "boho": ["boho", "bohemian", "crochet", "flowy", "floral", "fringe", "festival"],
    "minimal": ["minimal", "minimalist", "basic", "clean", "classic", "simple", "essential"],
    "elegant": ["elegant", "satin", "silk", "dressy", "chic", "evening", "polished", "classic", "midi", "heels"],
    "casual": ["casual", "everyday", "relaxed", "basic", "comfortable", "denim"],
    "classic": ["classic", "timeless", "tailored", "polished", "minimal"],
    "chic": ["chic", "elegant", "polished", "sleek", "modern"],
    "streetwear": ["streetwear", "oversized", "graphic", "sneakers", "urban"],
    "preppy": ["preppy", "polo", "pleated", "tailored", "classic"],
    "vintage": ["vintage", "retro"],
    "romantic": ["romantic", "lace", "floral", "ruffle", "feminine"],
    "sporty": ["sporty", "athletic", "active"],
    "edgy": ["edgy", "leather", "black", "moto"],
    "resort": ["resort", "vacation", "linen", "summer", "beach"],
    "dressy": ["dressy", "elegant", "evening", "satin", "heels"],
    "comfortable": ["comfortable", "comfy", "relaxed", "soft", "sneakers"],
}
STYLE_IMPLIES = {"beachy": ["coastal"], "coastal": ["beachy"]}

OCCASIONS = {
    "beach": ["beach", "swim", "resort", "summer", "sandals", "linen", "crochet", "breezy", "coastal"],
    "brunch": ["brunch", "casual", "day", "chic", "sundress", "linen", "summer"],
    "sightseeing": ["casual", "comfortable", "walking", "sneakers", "everyday", "day", "shorts"],
    "dinner": ["dinner", "evening", "dressy", "elegant", "night", "date", "satin", "midi", "heels"],
    "party": ["party", "night", "evening", "dressy", "satin", "sparkle"],
    "wedding": ["wedding", "elegant", "dressy", "formal", "midi", "satin"],
    "work": ["work", "office", "tailored", "polished", "classic", "blazer", "trousers"],
    "hiking": ["hiking", "athletic", "active", "outdoor", "comfortable", "sneakers"],
    "date": ["date", "evening", "romantic", "dressy", "elegant"],
    "concert": ["concert", "festival", "night", "edgy", "boho"],
    "casual": ["casual", "everyday", "relaxed", "comfortable"],
}
OCCASION_TITLES = {
    "beach": "Beach Day", "brunch": "Brunch", "sightseeing": "Sightseeing Day",
    "dinner": "Dinner Out", "party": "Night Out", "wedding": "Wedding Guest",
    "work": "Workday", "hiking": "Trail Day", "date": "Date Night", "concert": "Concert Night",
    "casual": "Everyday",
}
DRESS_OCCASIONS = {"dinner", "party", "wedding", "date"}

STOPWORDS = {"a", "an", "the", "and", "or", "of", "with", "for", "some", "one", "new", "my"}


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z\-]+", (text or "").lower()))


def product_text(item: dict) -> str:
    parts = [item.get("name") or "", item.get("subcategory") or "", item.get("description") or "",
             " ".join(item.get("tags") or []), " ".join(item.get("colors") or [])]
    return " ".join(parts).lower().replace("_", " ")


def term_in_text(term: str, text: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(term.lower()) + r"s?(?![a-z])", text) is not None


def expand_styles(styles: list[str]) -> set[str]:
    out: set[str] = set()
    for s in styles:
        s = s.lower()
        out.add(s)
        out.update(STYLES.get(s, []))
    return out


def expand_colors(colors: list[str]) -> set[str]:
    out: set[str] = set()
    for c in colors:
        c = c.lower()
        out.update(COLOR_GROUPS.get(c, {c}))
    return out


def garment_category(word: str) -> str | None:
    return GARMENTS.get(word.lower())


def kind_category(kind: str) -> str | None:
    """'crochet top' -> 'top', 'linen skirt' -> 'bottom'."""
    kind = kind.lower()
    if kind in GARMENTS:
        return GARMENTS[kind]
    for noun in sorted(GARMENTS, key=len, reverse=True):
        if term_in_text(noun, kind):
            return GARMENTS[noun]
    return None


def matches_kind(item: dict, kind: str) -> bool:
    """Does a product/wardrobe item satisfy a required item description like 'crochet top'?"""
    cat = kind_category(kind)
    if cat and item.get("category") != cat:
        return False
    text = product_text(item)
    for word in tokenize(kind):
        if word in STOPWORDS or word in GENERIC_CATEGORY_WORDS:
            continue
        if not term_in_text(word, text):
            return False
    return True
