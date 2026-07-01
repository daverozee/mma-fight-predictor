from __future__ import annotations

import json
import re
import struct
import urllib.parse
import urllib.request
from csv import DictReader
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
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
    "combat sport",
)
COMMONS_IMAGE_SEARCHES = (
    '"{name}" MMA fighter',
    '"{name}" mixed martial arts',
    '"{name}" UFC fighter',
    '"{name}" Bellator fighter',
    '"{name}" professional fighter',
)
MEDIA_OVERRIDES_PATH = Path(__file__).resolve().parent / "data" / "fighter_media_overrides.csv"
MIN_VISIBLE_IMAGE_SIZE = 64


@dataclass(frozen=True)
class ImageHealth:
    valid: bool
    width: int | None = None
    height: int | None = None
    reason: str | None = None


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
        .outerjoin(FighterProfile, FighterMedia.fighter_name == FighterProfile.name)
        .where(FighterMedia.status.in_(("generated", "missing", "broken")))
        .order_by(
            (
                func.coalesce(FighterProfile.wins, 0)
                + func.coalesce(FighterProfile.losses, 0)
            ).desc(),
            FighterMedia.fighter_name,
        )
    )
    if limit:
        query = query.limit(limit)

    found = missing = checked = 0
    for media in db.scalars(query):
        checked += 1
        result = public_fighter_thumbnail(media.fighter_name)
        media.fetched_at = datetime.utcnow()
        if result is None:
            media.status = "missing"
            media.source = "public-image-search"
            missing += 1
        else:
            media.thumbnail_url = result["thumbnail_url"]
            media.page_url = result["page_url"]
            media.source = result["source"]
            media.status = "found"
            found += 1
        if checked % 50 == 0:
            db.commit()
    db.commit()
    return {"checked": checked, "found": found, "missing": missing}


def improve_fighter_media(
    db: Session,
    seed_limit: int | None = None,
    wikimedia_limit: int = 25,
    verification_limit: int = 50,
    wikidata_bulk_limit: int = 500,
) -> dict[str, int]:
    generated = seed_generated_media(db, limit=seed_limit)
    wikidata = fetch_wikidata_mma_media(db, limit=wikidata_bulk_limit) if wikidata_bulk_limit else {
        "checked": 0,
        "matched": 0,
        "skipped": 0,
    }
    lookup = fetch_wikimedia_media(db, limit=wikimedia_limit) if wikimedia_limit else {
        "checked": 0,
        "found": 0,
        "missing": 0,
    }
    verified = verify_media_urls(db, limit=verification_limit) if verification_limit else {
        "checked": 0,
        "valid": 0,
        "broken": 0,
    }
    return {
        "generated": generated,
        "wikidata_checked": wikidata["checked"],
        "wikidata_matched": wikidata["matched"],
        "wikidata_skipped": wikidata["skipped"],
        "wikimedia_checked": lookup["checked"],
        "wikimedia_found": lookup["found"],
        "wikimedia_missing": lookup["missing"],
        "verified": verified["checked"],
        "valid": verified["valid"],
        "broken": verified["broken"],
    }


def verify_media_urls(db: Session, limit: int = 50) -> dict[str, int]:
    rows = db.scalars(
        select(FighterMedia)
        .where(
            FighterMedia.status.in_(("found", "broken")),
            FighterMedia.thumbnail_url.is_not(None),
        )
        .order_by(FighterMedia.fetched_at, FighterMedia.fighter_name)
        .limit(limit)
    ).all()

    checked = valid = broken = 0
    for media in rows:
        checked += 1
        health = image_url_health(media.thumbnail_url or "")
        media.fetched_at = datetime.utcnow()
        if health.valid:
            media.status = "found"
            valid += 1
        elif health.reason != "fetch_failed":
            media.status = "broken"
            broken += 1
        if checked % 25 == 0:
            db.commit()
    db.commit()
    return {"checked": checked, "valid": valid, "broken": broken}


def image_url_health(
    url: str,
    opener: Any = urllib.request.urlopen,
    timeout: int = 8,
    max_bytes: int = 512_000,
) -> ImageHealth:
    if not url.startswith(("http://", "https://")):
        return ImageHealth(valid=False, reason="unsupported_url")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "mma-fight-predictor/0.1 (image verification)",
            "Range": f"bytes=0-{max_bytes - 1}",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type", "")).lower()
            body = response.read(max_bytes)
    except Exception:  # noqa: BLE001
        return ImageHealth(valid=False, reason="fetch_failed")

    width, height = image_dimensions(body)
    if not content_type.startswith("image/") and width is None:
        return ImageHealth(valid=False, reason="not_image")
    if width is None or height is None:
        return ImageHealth(valid=False, reason="unknown_dimensions")
    if width < MIN_VISIBLE_IMAGE_SIZE or height < MIN_VISIBLE_IMAGE_SIZE:
        return ImageHealth(valid=False, width=width, height=height, reason="too_small")
    return ImageHealth(valid=True, width=width, height=height)


def image_dimensions(data: bytes) -> tuple[int | None, int | None]:
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", data[16:24])
    if len(data) >= 10 and data[:6] in {b"GIF87a", b"GIF89a"}:
        return struct.unpack("<HH", data[6:10])
    if len(data) >= 4 and data.startswith(b"\xff\xd8"):
        return jpeg_dimensions(data)
    if len(data) >= 30 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return webp_dimensions(data)
    return None, None


def jpeg_dimensions(data: bytes) -> tuple[int | None, int | None]:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            break
        length = int.from_bytes(data[index : index + 2], "big")
        if length < 2 or index + length > len(data):
            break
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return width, height
        index += length
    return None, None


def webp_dimensions(data: bytes) -> tuple[int | None, int | None]:
    chunk = data[12:16]
    if chunk == b"VP8 " and len(data) >= 30:
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    if chunk == b"VP8X" and len(data) >= 30:
        width = int.from_bytes(data[24:27] + b"\x00", "little") + 1
        height = int.from_bytes(data[27:30] + b"\x00", "little") + 1
        return width, height
    return None, None


def fetch_wikidata_mma_media(db: Session, limit: int | None = None) -> dict[str, int]:
    try:
        rows = wikidata_mma_image_rows(limit=limit)
    except Exception:  # noqa: BLE001
        return {"checked": 0, "matched": 0, "skipped": 0}
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


def import_media_overrides(db: Session, csv_path: Path = MEDIA_OVERRIDES_PATH) -> int:
    if not csv_path.exists():
        return 0

    profiles = {profile.name: profile.id for profile in db.scalars(select(FighterProfile)).all()}
    imported = 0
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        for row in DictReader(file):
            fighter_name = (row.get("fighter_name") or "").strip()
            thumbnail_url = (row.get("thumbnail_url") or "").strip()
            if not fighter_name or not thumbnail_url:
                continue
            media = db.scalar(select(FighterMedia).where(FighterMedia.fighter_name == fighter_name))
            if media is None:
                media = FighterMedia(fighter_name=fighter_name)
                db.add(media)
            media.fighter_profile_id = profiles.get(fighter_name)
            media.thumbnail_url = thumbnail_url
            media.page_url = (row.get("page_url") or "").strip() or None
            media.source = "curated-media-override"
            media.status = "found"
            media.fetched_at = datetime.utcnow()
            imported += 1
    db.commit()
    return imported


def public_fighter_thumbnail(
    name: str,
    opener: Any = urllib.request.urlopen,
) -> dict[str, str] | None:
    for lookup in (
        wikipedia_summary_thumbnail,
        wikidata_entity_thumbnail,
        commons_search_thumbnail,
    ):
        result = lookup(name, opener=opener)
        if result:
            return result
    return None


def wikimedia_thumbnail(name: str) -> dict[str, str] | None:
    return wikipedia_summary_thumbnail(name)


def wikipedia_summary_thumbnail(
    name: str,
    opener: Any = urllib.request.urlopen,
) -> dict[str, str] | None:
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(name)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mma-fight-predictor/0.1 (thumbnail lookup)"},
    )
    try:
        with opener(request, timeout=10) as response:
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
    return {
        "thumbnail_url": str(thumbnail_url),
        "page_url": str(page_url or ""),
        "source": "wikipedia-summary",
    }


def wikidata_entity_thumbnail(
    name: str,
    opener: Any = urllib.request.urlopen,
) -> dict[str, str] | None:
    for entity in wikidata_search_entities(name, opener=opener):
        if not wikidata_entity_is_likely_fighter(name, entity):
            continue
        image = wikidata_entity_image(entity["id"], opener=opener)
        if image:
            return image
    return None


def wikidata_search_entities(
    name: str,
    opener: Any = urllib.request.urlopen,
    limit: int = 5,
) -> list[dict[str, Any]]:
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "uselang": "en",
            "type": "item",
            "limit": limit,
            "search": name,
        }
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mma-fight-predictor/0.1 (wikidata entity image lookup)"},
    )
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    return [item for item in payload.get("search", []) if isinstance(item, dict)]


def wikidata_entity_is_likely_fighter(name: str, entity: dict[str, Any]) -> bool:
    labels = [entity.get("label"), entity.get("title")]
    aliases = entity.get("aliases") or []
    labels.extend(alias for alias in aliases if isinstance(alias, str))
    if not any(name_matches_label(name, str(label or "")) for label in labels):
        return False

    description = str(entity.get("description") or "").lower()
    return any(keyword in description for keyword in MEDIA_KEYWORDS)


def wikidata_entity_image(
    entity_id: str,
    opener: Any = urllib.request.urlopen,
) -> dict[str, str] | None:
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "wbgetentities",
            "format": "json",
            "ids": entity_id,
            "props": "claims|sitelinks",
            "sitefilter": "enwiki",
        }
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mma-fight-predictor/0.1 (wikidata entity image lookup)"},
    )
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

    entity = (payload.get("entities") or {}).get(entity_id) or {}
    claims = entity.get("claims") or {}
    image_claim = next(iter(claims.get("P18") or []), None)
    if not image_claim:
        return None
    value = (
        image_claim.get("mainsnak", {})
        .get("datavalue", {})
        .get("value")
    )
    if not value:
        return None

    page_url = f"https://www.wikidata.org/wiki/{urllib.parse.quote(entity_id)}"
    enwiki_title = (
        (entity.get("sitelinks") or {})
        .get("enwiki", {})
        .get("title")
    )
    if enwiki_title:
        page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(str(enwiki_title).replace(' ', '_'))}"
    return {
        "thumbnail_url": commons_file_url(str(value)),
        "page_url": page_url,
        "source": "wikidata-entity-image",
    }


def commons_search_thumbnail(
    name: str,
    opener: Any = urllib.request.urlopen,
) -> dict[str, str] | None:
    for search in COMMONS_IMAGE_SEARCHES:
        result = commons_image_search(search.format(name=name), name=name, opener=opener)
        if result:
            return result
    return None


def commons_image_search(
    search: str,
    name: str,
    opener: Any = urllib.request.urlopen,
    limit: int = 5,
) -> dict[str, str] | None:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "gsrsearch": search,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 160,
        }
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mma-fight-predictor/0.1 (commons image lookup)"},
    )
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

    pages = (payload.get("query") or {}).get("pages") or {}
    for page in pages.values():
        imageinfo = next(iter(page.get("imageinfo") or []), {})
        thumbnail_url = imageinfo.get("thumburl") or imageinfo.get("url")
        title = str(page.get("title") or "")
        if thumbnail_url and commons_result_matches_name(name, title, str(thumbnail_url)):
            return {
                "thumbnail_url": str(thumbnail_url),
                "page_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                "source": "commons-image-search",
            }
    return None


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


def commons_file_url(value: str) -> str:
    if value.startswith(("http://", "https://")):
        url = value.replace("http://commons.wikimedia.org/", "https://commons.wikimedia.org/")
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}width=160"

    filename = value.removeprefix("File:").replace(" ", "_")
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(filename)}?width=160"


def normalize_person_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def name_matches_label(name: str, label: str) -> bool:
    normalized_name = normalize_person_name(name)
    normalized_label = normalize_person_name(label)
    if normalized_name == normalized_label:
        return True
    name_parts = normalized_name.split()
    label_parts = normalized_label.split()
    return bool(name_parts) and all(part in label_parts for part in name_parts)


def commons_result_matches_name(name: str, title: str, thumbnail_url: str) -> bool:
    haystack = normalize_person_name(f"{title} {urllib.parse.unquote(thumbnail_url)}")
    name_parts = normalize_person_name(name).split()
    return bool(name_parts) and all(part in haystack for part in name_parts)


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
