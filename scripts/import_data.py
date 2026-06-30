from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_jobs import run_data_import_cycle  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.ingestion.connectors import DEFAULT_CATALOG_PATH  # noqa: E402


def main() -> None:
    catalog_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CATALOG_PATH
    init_db()
    with SessionLocal() as db:
        summary = run_data_import_cycle(db, catalog_path)

    print(f"Catalog: {catalog_path}")
    for source in summary.source_results:
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
        f"records={summary.records_seen}, "
        f"created={summary.profiles_created}, "
        f"updated={summary.profiles_updated}, "
        f"features_imported={summary.features_imported}, "
        f"profiles_promoted={summary.profiles_promoted}, "
        f"current_fights_imported={summary.current_fights_imported}, "
        f"media_overrides_imported={summary.media_overrides_imported}, "
        f"fighters_in_db={summary.fighters_in_db}, "
        f"external_features_in_db={summary.external_features_in_db}"
    )


if __name__ == "__main__":
    main()
