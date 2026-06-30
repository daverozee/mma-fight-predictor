from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.current_fights import import_current_fight_results
from app.fighters import promote_imported_fighters_to_profiles
from app.ingestion.connectors import (
    DEFAULT_CATALOG_PATH,
    SourceResult,
    import_catalog,
    ingestion_counts,
)
from app.media import import_media_overrides


@dataclass(frozen=True)
class DataImportSummary:
    records_seen: int
    profiles_created: int
    profiles_updated: int
    features_imported: int
    profiles_promoted: int
    current_fights_imported: int
    media_overrides_imported: int
    fighters_in_db: int
    external_features_in_db: int
    source_results: list[SourceResult]


def run_data_import_cycle(
    db: Session,
    catalog_path: str | Path = DEFAULT_CATALOG_PATH,
) -> DataImportSummary:
    result = import_catalog(db, catalog_path)
    promoted = promote_imported_fighters_to_profiles(db)
    current_fights = import_current_fight_results(db)
    media_overrides = import_media_overrides(db)
    counts = ingestion_counts(db)
    return DataImportSummary(
        records_seen=result.records_seen,
        profiles_created=result.profiles_created,
        profiles_updated=result.profiles_updated,
        features_imported=result.features_imported,
        profiles_promoted=promoted,
        current_fights_imported=current_fights,
        media_overrides_imported=media_overrides,
        fighters_in_db=counts["fighters"],
        external_features_in_db=counts["external_features"],
        source_results=result.sources,
    )
