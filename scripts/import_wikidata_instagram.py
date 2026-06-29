from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys
import urllib.parse
import urllib.request

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import FighterExternalFeature, FighterProfile  # noqa: E402
from app.social import normalize_instagram_url  # noqa: E402

SOURCE_NAME = "wikidata-instagram"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
SPARQL_QUERY = """
SELECT ?fighter ?fighterLabel ?instagram WHERE {
  {
    ?fighter wdt:P106/wdt:P279* wd:Q10841764.
  }
  UNION
  {
    ?fighter wdt:P641 wd:Q11420.
  }
  ?fighter wdt:P2003 ?instagram.
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Import fighter Instagram links from Wikidata.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    rows = fetch_wikidata_rows(args.limit)
    init_db()
    with SessionLocal() as db:
        profiles = {profile.name: profile for profile in db.scalars(select(FighterProfile)).all()}
        matched = updated = features = 0
        for row in rows:
            name = row["name"]
            profile = profiles.get(name)
            instagram_url = normalize_instagram_url(row["instagram"])
            if profile is None or instagram_url is None:
                continue

            matched += 1
            if profile.instagram_url != instagram_url:
                profile.instagram_url = instagram_url
                updated += 1
            features += upsert_instagram_feature(
                db,
                profile,
                instagram_url,
                source_record_id=row["wikidata_id"],
                source_url=row["wikidata_url"],
            )
        db.commit()

    print(f"Wikidata Instagram rows seen: {len(rows)}")
    print(f"Matched fighter profiles: {matched}")
    print(f"Profiles updated: {updated}")
    print(f"External features upserted: {features}")


def fetch_wikidata_rows(limit: int | None = None) -> list[dict[str, str]]:
    query = SPARQL_QUERY
    if limit:
        query = f"{query}\nLIMIT {limit}"
    url = f"{SPARQL_ENDPOINT}?{urllib.parse.urlencode({'query': query, 'format': 'json'})}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mma-fight-predictor/0.1 (instagram import)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))

    rows = []
    for binding in payload["results"]["bindings"]:
        wikidata_url = binding["fighter"]["value"]
        rows.append(
            {
                "name": binding["fighterLabel"]["value"].strip(),
                "instagram": binding["instagram"]["value"].strip(),
                "wikidata_url": wikidata_url,
                "wikidata_id": wikidata_url.rsplit("/", 1)[-1],
            }
        )
    return rows


def upsert_instagram_feature(
    db,
    profile: FighterProfile,
    instagram_url: str,
    source_record_id: str,
    source_url: str,
) -> int:
    existing = db.scalar(
        select(FighterExternalFeature).where(
            FighterExternalFeature.fighter_name == profile.name,
            FighterExternalFeature.feature_name == "instagram_url",
            FighterExternalFeature.source == SOURCE_NAME,
        )
    )
    if existing is None:
        db.add(
            FighterExternalFeature(
                fighter_profile_id=profile.id,
                fighter_name=profile.name,
                feature_name="instagram_url",
                text_value=instagram_url,
                source=SOURCE_NAME,
                source_url=source_url,
                source_record_id=source_record_id,
            )
        )
    else:
        existing.fighter_profile_id = profile.id
        existing.text_value = instagram_url
        existing.source_url = source_url
        existing.source_record_id = source_record_id
    return 1


if __name__ == "__main__":
    main()
