from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import FighterExternalFeature, FighterProfile  # noqa: E402
from app.social import normalize_instagram_url  # noqa: E402

GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
SOURCE_NAME = "google-cse-instagram-discovery"
DEFAULT_MIN_SCORE = 72
DEFAULT_REVIEW_SCORE = 45
MMA_TERMS = {
    "bellator",
    "fighter",
    "mma",
    "mixed martial arts",
    "one championship",
    "pfl",
    "rizin",
    "ufc",
}
LOW_CONFIDENCE_TERMS = {
    "edit",
    "fan",
    "fanpage",
    "highlights",
    "meme",
    "news",
    "parody",
    "podcast",
}


@dataclass(frozen=True)
class SocialCandidate:
    fighter_name: str
    url: str
    handle: str
    score: int
    title: str
    snippet: str
    query: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover fighter Instagram links with Google Custom Search JSON API."
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--include-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--review-score", type=int, default=DEFAULT_REVIEW_SCORE)
    parser.add_argument("--results-per-query", type=int, default=5)
    parser.add_argument("--queries-per-fighter", type=int, default=2)
    parser.add_argument("--delay-seconds", type=float, default=0.2)
    args = parser.parse_args()

    api_key = require_env("GOOGLE_SEARCH_API_KEY")
    engine_id = require_env("GOOGLE_SEARCH_ENGINE_ID")

    init_db()
    with SessionLocal() as db:
        fighters = selected_fighters(
            db,
            names=args.name,
            include_existing=args.include_existing,
            limit=args.limit,
            offset=args.offset,
        )
        searched = saved = review = 0
        for fighter in fighters:
            candidate = best_candidate_for_fighter(
                fighter.name,
                api_key=api_key,
                engine_id=engine_id,
                results_per_query=args.results_per_query,
                queries_per_fighter=args.queries_per_fighter,
                delay_seconds=args.delay_seconds,
            )
            searched += 1
            if candidate is None:
                print(f"{fighter.name}: no candidate")
                continue

            print(
                f"{fighter.name}: {candidate.url} "
                f"score={candidate.score} title={candidate.title[:80]!r}"
            )
            if args.dry_run:
                continue

            if candidate.score >= args.min_score:
                fighter.instagram_url = candidate.url
                upsert_candidate_features(db, fighter, candidate, accepted=True)
                saved += 1
            elif candidate.score >= args.review_score:
                upsert_candidate_features(db, fighter, candidate, accepted=False)
                review += 1

            if searched % 25 == 0:
                db.commit()
        if not args.dry_run:
            db.commit()

    print(f"Fighters searched: {searched}")
    print(f"Instagram links saved: {saved}")
    print(f"Candidates stored for review: {review}")


def selected_fighters(
    db,
    names: list[str],
    include_existing: bool,
    limit: int,
    offset: int,
) -> list[FighterProfile]:
    query = select(FighterProfile).order_by(FighterProfile.name)
    if names:
        query = query.where(FighterProfile.name.in_(names))
    elif not include_existing:
        query = query.where(FighterProfile.instagram_url.is_(None))
    return list(db.scalars(query.offset(offset).limit(limit)).all())


def best_candidate_for_fighter(
    fighter_name: str,
    api_key: str,
    engine_id: str,
    results_per_query: int,
    queries_per_fighter: int,
    delay_seconds: float,
) -> SocialCandidate | None:
    candidates: list[SocialCandidate] = []
    for query in search_queries(fighter_name)[:queries_per_fighter]:
        for item in google_search(api_key, engine_id, query, results_per_query):
            candidate = score_item(fighter_name, item, query)
            if candidate is not None:
                candidates.append(candidate)
        if delay_seconds:
            time.sleep(delay_seconds)
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate.score)


def search_queries(fighter_name: str) -> list[str]:
    return [
        f'site:instagram.com "{fighter_name}" MMA',
        f'site:instagram.com "{fighter_name}" UFC',
        f'"{fighter_name}" official Instagram MMA fighter',
    ]


def google_search(api_key: str, engine_id: str, query: str, results_per_query: int) -> list[dict]:
    params = {
        "key": api_key,
        "cx": engine_id,
        "q": query,
        "num": max(1, min(results_per_query, 10)),
    }
    url = f"{GOOGLE_CSE_ENDPOINT}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mma-fight-predictor/0.1 (social discovery)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("items", [])


def score_item(fighter_name: str, item: dict, query: str) -> SocialCandidate | None:
    url = normalize_instagram_url(item.get("link") or item.get("formattedUrl"))
    if url is None:
        return None

    handle = url.rstrip("/").rsplit("/", 1)[-1]
    title = clean_text(item.get("title"))
    snippet = clean_text(item.get("snippet"))
    haystack = f"{title} {snippet} {handle.replace('.', ' ').replace('_', ' ')}"
    haystack_normalized = normalize_text(haystack)
    name_normalized = normalize_text(fighter_name)
    name_tokens = significant_tokens(fighter_name)
    haystack_tokens = set(significant_tokens(haystack))
    handle_tokens = set(significant_tokens(handle.replace(".", " ").replace("_", " ")))

    score = 0
    if name_normalized and name_normalized in haystack_normalized:
        score += 35
    overlap = set(name_tokens) & haystack_tokens
    if name_tokens:
        score += round(30 * len(overlap) / len(name_tokens))
    handle_overlap = set(name_tokens) & handle_tokens
    if name_tokens:
        score += round(25 * len(handle_overlap) / len(name_tokens))
    if any(term in haystack_normalized for term in MMA_TERMS):
        score += 12
    if "instagram" in normalize_text(title):
        score += 5
    if "official" in haystack_normalized:
        score += 4
    low_confidence_page = any(term in haystack_normalized for term in LOW_CONFIDENCE_TERMS)
    if low_confidence_page and not handle_overlap:
        return None
    if low_confidence_page:
        score -= 25

    score = max(0, min(score, 100))
    if score < DEFAULT_REVIEW_SCORE:
        return None
    return SocialCandidate(
        fighter_name=fighter_name,
        url=url,
        handle=handle,
        score=score,
        title=title,
        snippet=snippet,
        query=query,
    )


def upsert_candidate_features(
    db,
    fighter: FighterProfile,
    candidate: SocialCandidate,
    accepted: bool,
) -> None:
    feature_values = {
        "instagram_url": candidate.url if accepted else None,
        "instagram_candidate_url": candidate.url,
        "instagram_candidate_score": float(candidate.score),
        "instagram_candidate_title": candidate.title,
        "instagram_candidate_query": candidate.query,
        "instagram_candidate_status": "accepted" if accepted else "review",
    }
    for feature_name, value in feature_values.items():
        if value is None:
            continue
        numeric_value = value if isinstance(value, float) else None
        text_value = None if numeric_value is not None else str(value)
        existing = db.scalar(
            select(FighterExternalFeature).where(
                FighterExternalFeature.fighter_name == fighter.name,
                FighterExternalFeature.feature_name == feature_name,
                FighterExternalFeature.source == SOURCE_NAME,
            )
        )
        if existing is None:
            db.add(
                FighterExternalFeature(
                    fighter_profile_id=fighter.id,
                    fighter_name=fighter.name,
                    feature_name=feature_name,
                    numeric_value=numeric_value,
                    text_value=text_value,
                    source=SOURCE_NAME,
                    source_url=candidate.url,
                    source_record_id=candidate.handle,
                )
            )
        else:
            existing.fighter_profile_id = fighter.id
            existing.numeric_value = numeric_value
            existing.text_value = text_value
            existing.source_url = candidate.url
            existing.source_record_id = candidate.handle


def significant_tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", normalize_text(value)) if len(token) > 1]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Set {name} before running social discovery.")
    return value


if __name__ == "__main__":
    main()
