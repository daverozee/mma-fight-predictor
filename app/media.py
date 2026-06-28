from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Iterable
from datetime import datetime
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FighterMedia, FighterProfile

MEDIA_KEYWORDS = (
    "mixed martial",
    "mma",
    "ultimate fighting",
    "ufc",
    "bellator",
    "professional fighter",
    "martial artist",
)


def seed_generated_media(db: Session, limit: int | None = None) -> int:
    query = (
        select(FighterProfile)
        .where(FighterProfile.name.not_in(select(FighterMedia.fighter_name)))
        .order_by(FighterProfile.name)
    )
    if limit:
        query = query.limit(limit)

    created = 0
    for fighter in db.scalars(query):
        db.add(
            FighterMedia(
                fighter_profile_id=fighter.id,
                fighter_name=fighter.name,
                source="generated-fallback",
                status="generated",
            )
        )
        created += 1
        if created % 500 == 0:
            db.commit()
    db.commit()
    return created


def fetch_wikimedia_media(db: Session, limit: int | None = None) -> dict[str, int]:
    query = (
        select(FighterMedia)
        .where(FighterMedia.status.in_(("generated", "missing")))
        .order_by(FighterMedia.fighter_name)
    )
    if limit:
        query = query.limit(limit)

    found = missing = checked = 0
    for media in db.scalars(query):
        checked += 1
        result = wikimedia_thumbnail(media.fighter_name)
        media.fetched_at = datetime.utcnow()
        if result is None:
            media.status = "missing"
            media.source = "wikimedia-summary"
            missing += 1
        else:
            media.thumbnail_url = result["thumbnail_url"]
            media.page_url = result["page_url"]
            media.source = "wikimedia-summary"
            media.status = "found"
            found += 1
        if checked % 50 == 0:
            db.commit()
    db.commit()
    return {"checked": checked, "found": found, "missing": missing}


def fetch_wikidata_mma_media(db: Session, limit: int | None = None) -> dict[str, int]:
    rows = wikidata_mma_image_rows(limit=limit)
    media_by_name = {
        row.fighter_name.lower(): row
        for row in db.scalars(select(FighterMedia)).all()
    }
    matched = skipped = 0
    for row in rows:
        name = row["name"].strip()
        media = media_by_name.get(name.lower())
        if media is None:
            skipped += 1
            continue
        media.thumbnail_url = row["image_url"]
        media.page_url = row["page_url"]
        media.source = "wikidata-commons"
        media.status = "found"
        media.fetched_at = datetime.utcnow()
        matched += 1
        if matched % 100 == 0:
            db.commit()
    db.commit()
    return {"checked": len(rows), "matched": matched, "skipped": skipped}


def wikimedia_thumbnail(name: str) -> dict[str, str] | None:
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(name)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mma-fight-predictor/0.1 (thumbnail lookup)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

    extract = str(payload.get("extract") or "").lower()
    if not any(keyword in extract for keyword in MEDIA_KEYWORDS):
        return None
    thumbnail = payload.get("thumbnail") or {}
    thumbnail_url = thumbnail.get("source")
    page_url = (payload.get("content_urls") or {}).get("desktop", {}).get("page")
    if not thumbnail_url:
        return None
    return {"thumbnail_url": str(thumbnail_url), "page_url": str(page_url or "")}


def wikidata_mma_image_rows(limit: int | None = None) -> list[dict[str, str]]:
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    query = f"""
SELECT ?person ?personLabel ?image WHERE {{
  ?person wdt:P31 wd:Q5;
          wdt:P106 wd:Q11607585;
          wdt:P18 ?image.
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
{limit_clause}
"""
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode(
        {"format": "json", "query": query}
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mma-fight-predictor/0.1 (wikidata image import)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = []
    seen_names = set()
    for binding in payload.get("results", {}).get("bindings", []):
        name = binding.get("personLabel", {}).get("value")
        image_url = binding.get("image", {}).get("value")
        page_url = binding.get("person", {}).get("value")
        if not name or not image_url or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        rows.append(
            {
                "name": str(name),
                "image_url": commons_file_url(str(image_url)),
                "page_url": str(page_url or ""),
            }
        )
    return rows


def commons_file_url(url: str) -> str:
    url = url.replace("http://commons.wikimedia.org/", "https://commons.wikimedia.org/")
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}width=160"


def media_url_for_name(media: FighterMedia | None, name: str) -> str:
    if media and media.thumbnail_url and media.status == "found":
        return media.thumbnail_url
    return fallback_thumbnail_url(name)


def media_map_for_names(db: Session, names: Iterable[str]) -> dict[str, FighterMedia]:
    unique_names = sorted({name for name in names if name})
    rows: dict[str, FighterMedia] = {}
    for chunk in chunks(unique_names, 500):
        for row in db.scalars(select(FighterMedia).where(FighterMedia.fighter_name.in_(chunk))):
            rows[row.fighter_name] = row
    return rows


def fighter_thumbnail_urls(db: Session, fighters: Iterable[object]) -> dict[str, str]:
    fighter_list = list(fighters)
    return thumbnail_urls_for_names(db, [fighter.name for fighter in fighter_list])


def thumbnail_urls_for_names(db: Session, names: Iterable[str]) -> dict[str, str]:
    name_list = list(names)
    media_rows = media_map_for_names(db, name_list)
    return {name: media_url_for_name(media_rows.get(name), name) for name in name_list}


def fallback_thumbnail_url(name: str) -> str:
    return f"/api/v1/fighter-thumbnail.svg?name={urllib.parse.quote(name)}"


def avatar_svg(name: str) -> str:
    initials = fighter_initials(name)
    color = color_for_name(name)
    escaped_name = escape(name)
    escaped_initials = escape(initials)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128" role="img" aria-label="{escaped_name}">
  <rect width="128" height="128" rx="18" fill="{color}"/>
  <path d="M0 94 L128 44 L128 128 L0 128 Z" fill="rgba(0,0,0,0.18)"/>
  <circle cx="100" cy="28" r="20" fill="rgba(255,255,255,0.13)"/>
  <text x="64" y="76" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="34" font-weight="800" fill="#ffffff">{escaped_initials}</text>
</svg>"""


def fighter_initials(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", name)
    if not parts:
        return "MMA"
    if len(parts) == 1:
        return parts[0][:3].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


def color_for_name(name: str) -> str:
    palette = [
        "#0f6d50",
        "#b42126",
        "#2d69a6",
        "#7b2d63",
        "#a2652f",
        "#3d4a5b",
        "#7b8b3a",
        "#2f8892",
    ]
    return palette[sum(ord(char) for char in name) % len(palette)]


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]
