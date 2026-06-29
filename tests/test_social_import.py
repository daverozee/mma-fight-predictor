from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import FighterExternalFeature, FighterProfile
from scripts.import_social_links import import_social_links


def test_import_social_links_updates_matching_profiles() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add(profile("Ciryl Gane"))
        db.commit()

        result = import_social_links(
            db,
            [{"name": "Ciryl Gane", "instagram_url": "@ciryl_gane"}],
            source_url="test.csv",
        )
        db.commit()

        fighter = db.scalar(select(FighterProfile).where(FighterProfile.name == "Ciryl Gane"))
        feature = db.scalar(
            select(FighterExternalFeature).where(
                FighterExternalFeature.fighter_name == "Ciryl Gane",
                FighterExternalFeature.feature_name == "instagram_url",
            )
        )

    assert result == {"rows_seen": 1, "matched": 1, "updated": 1, "skipped": 0}
    assert fighter is not None
    assert fighter.instagram_url == "https://www.instagram.com/ciryl_gane/"
    assert feature is not None
    assert feature.text_value == "https://www.instagram.com/ciryl_gane/"


def profile(name: str) -> FighterProfile:
    return FighterProfile(
        name=name,
        weight_class="Heavyweight",
        age=35,
        height_cm=193,
        reach_cm=206,
        wins=12,
        losses=2,
        ko_rate=0.3,
        submission_rate=0.2,
        takedown_accuracy=0.4,
        takedown_defense=0.7,
        strikes_landed_per_min=5.4,
        strikes_absorbed_per_min=2.2,
        source="test",
    )
