from __future__ import annotations

import re
from urllib.parse import urlparse

INSTAGRAM_BASE_URL = "https://www.instagram.com"
INSTAGRAM_HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9._]{1,30}$")
INSTAGRAM_RESERVED_PATHS = {
    "about",
    "accounts",
    "challenge",
    "developer",
    "direct",
    "explore",
    "legal",
    "oauth",
    "p",
    "privacy",
    "reel",
    "reels",
    "stories",
    "tags",
    "terms",
    "tv",
}


def normalize_instagram_url(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None

    if text.startswith("@"):
        text = text[1:]

    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        if not parsed.netloc.lower().endswith("instagram.com"):
            return None
        text = parsed.path.strip("/").split("/", 1)[0]

    handle = text.strip().strip("/")
    if handle.lower() in INSTAGRAM_RESERVED_PATHS:
        return None
    if not handle or not INSTAGRAM_HANDLE_PATTERN.fullmatch(handle):
        return None
    return f"{INSTAGRAM_BASE_URL}/{handle}/"
