from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.ingestion.connectors import DEFAULT_CATALOG_PATH, import_catalog, ingestion_counts  # noqa: E402


def main() -> None:
    catalog_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CATALOG_PATH
    init_db()
    with SessionLocal() as db:
        result = import_catalog(db, catalog_path)
        counts = ingestion_counts(db)

    print(f"Catalog: {catalog_path}")
    for source in result.sources:
        print(
            f"{source.source_name}: {source.status}, "
            f"records={source.records_seen}, "
            f"created={source.profiles_created}, "
            f"updated={source.profiles_updated}, "
            f"features={source.features_imported}"
        )
        if source.error:
            print(f"  error={source.error}")
    print(
        "Totals: "
        f"records={result.records_seen}, "
        f"created={result.profiles_created}, "
        f"updated={result.profiles_updated}, "
        f"features_imported={result.features_imported}, "
        f"fighters_in_db={counts['fighters']}, "
        f"external_features_in_db={counts['external_features']}"
    )


if __name__ == "__main__":
    main()
