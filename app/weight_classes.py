from __future__ import annotations

import re

WEIGHT_CLASS_LIMITS_LBS = {
    "Strawweight": 115,
    "Flyweight": 125,
    "Bantamweight": 135,
    "Featherweight": 145,
    "Lightweight": 155,
    "Welterweight": 170,
    "Middleweight": 185,
    "Light Heavyweight": 205,
    "Heavyweight": 265,
}


def weight_class_limit_lbs(weight_class: str | None) -> int | None:
    canonical = canonical_weight_class(weight_class)
    if canonical is None:
        return None
    return WEIGHT_CLASS_LIMITS_LBS[canonical]


def canonical_weight_class(weight_class: str | None) -> str | None:
    if not weight_class:
        return None
    normalized = normalize_weight_class(weight_class)
    if "light heavyweight" in normalized:
        return "Light Heavyweight"
    if "straw" in normalized:
        return "Strawweight"
    if "fly" in normalized:
        return "Flyweight"
    if "bantam" in normalized:
        return "Bantamweight"
    if "feather" in normalized:
        return "Featherweight"
    if "light" in normalized:
        return "Lightweight"
    if "welter" in normalized:
        return "Welterweight"
    if "middle" in normalized:
        return "Middleweight"
    if "heavy" in normalized:
        return "Heavyweight"
    return None


def normalize_weight_class(weight_class: str) -> str:
    normalized = weight_class.lower().replace("women's", "").replace("womens", "")
    normalized = normalized.replace("women", "").replace("ufc", "")
    normalized = re.sub(r"[^a-z\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
