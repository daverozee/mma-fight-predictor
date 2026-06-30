from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.current_fights import import_current_fight_results
from app.fighters import promote_imported_fighters_to_profiles
from app.ingestion.connectors import (
    DEFAULT_CATALOG_PATH,
    SourceResult,
    import_catalog,
    ingestion_counts,
)
from app.media import import_media_overrides, improve_fighter_media
from scripts.import_fight_results import import_fight_results_from_args


@dataclass(frozen=True)
class DataImportSummary:
    records_seen: int
    profiles_created: int
    profiles_updated: int
    features_imported: int
    profiles_promoted: int
    current_fights_imported: int
    historical_fights_imported: int
    media_overrides_imported: int
    fighters_in_db: int
    external_features_in_db: int
    media_improvement: dict[str, int]
    source_results: list[SourceResult]


def run_data_import_cycle(
    db: Session,
    catalog_path: str | Path = DEFAULT_CATALOG_PATH,
) -> DataImportSummary:
    result = import_catalog(db, catalog_path)
    promoted = promote_imported_fighters_to_profiles(db)
    current_fights = import_current_fight_results(db)
    settings = get_settings()
    historical_fights = import_configured_historical_fights(db, settings)
    media_overrides = import_media_overrides(db)
    media_improvement = improve_fighter_media(
        db,
        seed_limit=settings.media_seed_limit,
        wikimedia_limit=settings.media_wikimedia_lookup_limit,
        verification_limit=settings.media_verification_limit,
    )
    counts = ingestion_counts(db)
    return DataImportSummary(
        records_seen=result.records_seen,
        profiles_created=result.profiles_created,
        profiles_updated=result.profiles_updated,
        features_imported=result.features_imported,
        profiles_promoted=promoted,
        current_fights_imported=current_fights,
        historical_fights_imported=historical_fights,
        media_overrides_imported=media_overrides,
        fighters_in_db=counts["fighters"],
        external_features_in_db=counts["external_features"],
        media_improvement=media_improvement,
        source_results=result.sources,
    )


def import_configured_historical_fights(db: Session, settings: object) -> int:
    source_url = getattr(settings, "historical_fight_results_url", None)
    if not source_url:
        return 0
    args = Namespace(
        csv_path=source_url,
        format=getattr(settings, "historical_fight_results_format", "winner-loser"),
        winner_column="winner_name",
        loser_column="loser_name",
        event_column="event_name",
        date_column="bout_date",
        method_column="method",
        events_csv=getattr(settings, "historical_fight_results_events_url", None),
        source=getattr(settings, "historical_fight_results_source", "configured-fight-history"),
        source_url=source_url,
        allow_source_duplicates=False,
    )
    return import_fight_results_from_args(db, args).imported
