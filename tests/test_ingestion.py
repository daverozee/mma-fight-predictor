import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.fighters import (
    features_for_fighter,
    profile_to_features,
    promote_imported_fighters_to_profiles,
)
from app.ingestion.connectors import flatten_record, import_catalog, source_enabled, with_query_params
from app.models import FighterExternalFeature, FighterProfile


def test_open_catalog_imports_csv_and_json_sources(tmp_path: Path) -> None:
    csv_path = tmp_path / "fighters.csv"
    csv_path.write_text(
        "\n".join(
            [
                "name,age,height_cm,reach_cm,wins,losses,ko_rate,submission_rate,"
                "takedown_accuracy,takedown_defense,strikes_landed_per_min,"
                "strikes_absorbed_per_min,instagram,camp",
                "Test Striker,28,180,184,12,2,0.5,0.1,0.4,0.7,5.2,3.0,@teststriker,Sharp Gym",
            ]
        ),
        encoding="utf-8",
    )
    json_path = tmp_path / "supplemental.json"
    json_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "fighter": "Test Striker",
                        "elo": 1710,
                        "recent_fights": 3,
                        "stance": "Orthodox",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "name": "test-csv",
                        "format": "csv",
                        "location": str(csv_path),
                        "profile_mapping": {
                            "name": "name",
                            "age": "age",
                            "height_cm": "height_cm",
                            "reach_cm": "reach_cm",
                            "wins": "wins",
                            "losses": "losses",
                            "ko_rate": "ko_rate",
                            "submission_rate": "submission_rate",
                            "takedown_accuracy": "takedown_accuracy",
                            "takedown_defense": "takedown_defense",
                            "strikes_landed_per_min": "strikes_landed_per_min",
                            "strikes_absorbed_per_min": "strikes_absorbed_per_min",
                            "instagram_url": "instagram",
                        },
                        "extra_feature_mode": "all_unmapped",
                    },
                    {
                        "name": "test-json",
                        "format": "json",
                        "location": str(json_path),
                        "record_path": "items",
                        "profile_mapping": {"name": "fighter"},
                        "extra_feature_mode": "all_unmapped",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        result = import_catalog(db, catalog_path)

        profile = db.scalar(select(FighterProfile).where(FighterProfile.name == "Test Striker"))
        features = list(
            db.scalars(
                select(FighterExternalFeature).where(
                    FighterExternalFeature.fighter_name == "Test Striker"
                )
            )
        )

    assert result.records_seen == 2
    assert result.profiles_created == 1
    assert profile is not None
    assert profile.instagram_url == "https://www.instagram.com/teststriker/"
    assert {feature.feature_name for feature in features} >= {
        "test_csv_camp",
        "test_json_elo",
        "test_json_stance",
    }


def test_imported_fighters_can_be_promoted_to_provisional_profiles(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add_all(
            [
                FighterExternalFeature(
                    fighter_name="Live Fighter",
                    feature_name="balldontlie_fighters_live_date_of_birth",
                    text_value="1990-01-01T00:00:00.000Z",
                    source="balldontlie-fighters-live",
                ),
                FighterExternalFeature(
                    fighter_name="Live Fighter",
                    feature_name="balldontlie_fighters_live_height_inches",
                    numeric_value=70,
                    source="balldontlie-fighters-live",
                ),
                FighterExternalFeature(
                    fighter_name="Live Fighter",
                    feature_name="balldontlie_fighters_live_weight_class_abbreviation",
                    text_value="LW",
                    source="balldontlie-fighters-live",
                ),
            ]
        )
        db.commit()

        promoted = promote_imported_fighters_to_profiles(db)
        profile = db.scalar(select(FighterProfile).where(FighterProfile.name == "Live Fighter"))

    assert promoted == 1
    assert profile is not None
    assert profile.source == "provisional-live-feed"
    assert profile.weight_class == "Lightweight"
    assert profile.height_cm == 177.8
    assert profile.wins == 10


def test_existing_unknown_profile_uses_external_weight_context() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add(
            FighterProfile(
                name="Josh Hokit",
                weight_class="Unknown",
                age=30,
                height_cm=176,
                reach_cm=180,
                wins=10,
                losses=3,
                ko_rate=0.34,
                submission_rate=0.22,
                takedown_accuracy=0.45,
                takedown_defense=0.69,
                strikes_landed_per_min=4.4,
                strikes_absorbed_per_min=3.4,
                source="test",
            )
        )
        db.add_all(
            [
                FighterExternalFeature(
                    fighter_name="Josh Hokit",
                    feature_name="balldontlie_fighters_live_weight_class_abbreviation",
                    text_value="HW",
                    source="test",
                ),
                FighterExternalFeature(
                    fighter_name="Josh Hokit",
                    feature_name="balldontlie_fighters_live_weight_lbs",
                    numeric_value=231,
                    source="test",
                ),
            ]
        )
        db.commit()

        promote_imported_fighters_to_profiles(db)
        profile = db.scalar(select(FighterProfile).where(FighterProfile.name == "Josh Hokit"))
        features = profile_to_features(profile, features_for_fighter(db, profile.name))

    assert profile.weight_class == "Heavyweight"
    assert features.weight_class == "Heavyweight"
    assert features.weight_lbs == 231


def test_live_sources_can_be_env_gated(monkeypatch) -> None:
    source = {"name": "live", "enabled": True, "enabled_env": "MMA_TEST_KEY"}

    monkeypatch.delenv("MMA_TEST_KEY", raising=False)
    assert source_enabled(source) is False

    monkeypatch.setenv("MMA_TEST_KEY", "secret")
    assert source_enabled(source) is True


def test_json_flattening_and_query_params_support_api_catalogs() -> None:
    record = flatten_record({"name": "A", "weight_class": {"name": "Lightweight"}})
    url = with_query_params(
        "https://example.test/fighters?per_page=50",
        {"cursor": 123, "per_page": 100, "skip": None},
    )

    assert record["weight_class.name"] == "Lightweight"
    assert record["name"] == "A"
    assert url == "https://example.test/fighters?per_page=100&cursor=123"
