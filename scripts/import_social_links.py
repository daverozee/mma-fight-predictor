from __future__ import annotations

from pathlib import Path
import argparse
import csv
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import FighterExternalFeature, FighterProfile  # noqa: E402
from app.social import normalize_instagram_url  # noqa: E402

DEFAULT_SOCIAL_LINKS_PATH = ROOT / "app" / "data" / "fighter_social_links.csv"
SOURCE_NAME = "curated-social-links"


def main() -> None:
    parser = argparse.ArgumentParser(description="Import curated fighter social profile links.")
    parser.add_argument("csv_path", nargs="?", default=str(DEFAULT_SOCIAL_LINKS_PATH))
    parser.add_argument("--source", default=SOURCE_NAME)
    args = parser.parse_args()

    init_db()
    rows = load_rows(Path(args.csv_path))
    with SessionLocal() as db:
        result = import_social_links(db, rows, args.source, str(args.csv_path))
        db.commit()

    print(f"Social rows seen: {result['rows_seen']}")
    print(f"Profiles matched: {result['matched']}")
    print(f"Profiles updated: {result['updated']}")
    print(f"Rows skipped: {result['skipped']}")


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def import_social_links(
    db,
    rows: list[dict[str, str]],
    source: str = SOURCE_NAME,
    source_url: str | None = None,
) -> dict[str, int]:
    rows_seen = matched = updated = skipped = 0
    for row in rows:
        rows_seen += 1
        name = (row.get("name") or "").strip()
        instagram_url = normalize_instagram_url(row.get("instagram_url") or row.get("instagram"))
        if not name or instagram_url is None:
            skipped += 1
            continue

        profile = db.scalar(select(FighterProfile).where(FighterProfile.name == name))
        if profile is None:
            skipped += 1
            continue

        matched += 1
        if profile.instagram_url != instagram_url:
            profile.instagram_url = instagram_url
            updated += 1
        upsert_instagram_feature(db, profile, instagram_url, source, source_url)

    return {
        "rows_seen": rows_seen,
        "matched": matched,
        "updated": updated,
        "skipped": skipped,
    }


def upsert_instagram_feature(
    db,
    profile: FighterProfile,
    instagram_url: str,
    source: str,
    source_url: str | None,
) -> None:
    existing = db.scalar(
        select(FighterExternalFeature).where(
            FighterExternalFeature.fighter_name == profile.name,
            FighterExternalFeature.feature_name == "instagram_url",
            FighterExternalFeature.source == source,
        )
    )
    if existing is None:
        db.add(
            FighterExternalFeature(
                fighter_profile_id=profile.id,
                fighter_name=profile.name,
                feature_name="instagram_url",
                text_value=instagram_url,
                source=source,
                source_url=source_url,
                source_record_id=profile.name,
            )
        )
    else:
        existing.fighter_profile_id = profile.id
        existing.text_value = instagram_url
        existing.source_url = source_url
        existing.source_record_id = profile.name


if __name__ == "__main__":
    main()
