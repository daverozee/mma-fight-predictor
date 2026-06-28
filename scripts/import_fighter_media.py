from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.media import fetch_wikidata_mma_media, fetch_wikimedia_media, seed_generated_media  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Import fighter thumbnail metadata.")
    parser.add_argument(
        "--wikimedia-limit",
        type=int,
        default=0,
        help="Number of generated/missing media rows to check against Wikimedia.",
    )
    parser.add_argument(
        "--wikidata-limit",
        type=int,
        default=0,
        help="Number of Wikidata MMA image rows to import. Default 0 skips Wikidata.",
    )
    parser.add_argument(
        "--seed-limit",
        type=int,
        default=0,
        help="Number of fighters to seed with generated media rows. Default seeds all missing.",
    )
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        generated = seed_generated_media(db, limit=args.seed_limit or None)
        print(f"Generated thumbnail rows created: {generated}")
        if args.wikimedia_limit:
            result = fetch_wikimedia_media(db, limit=args.wikimedia_limit)
            print(
                "Wikimedia lookup: "
                f"checked={result['checked']}, found={result['found']}, missing={result['missing']}"
            )
        if args.wikidata_limit:
            result = fetch_wikidata_mma_media(db, limit=args.wikidata_limit)
            print(
                "Wikidata MMA images: "
                f"checked={result['checked']}, matched={result['matched']}, skipped={result['skipped']}"
            )


if __name__ == "__main__":
    main()
