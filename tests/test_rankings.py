import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import FighterProfile
from app.rankings import load_rankings


def test_load_rankings_links_entries_to_fighter_profiles(tmp_path) -> None:
    rankings_path = tmp_path / "rankings.json"
    rankings_path.write_text(
        json.dumps(
            {
                "updated": "2026-06-29",
                "promotions": [
                    {
                        "name": "UFC",
                        "source_label": "Official rankings",
                        "source_url": "https://www.ufc.com/rankings",
                        "summary": "Official source",
                        "divisions": [
                            {
                                "name": "Heavyweight",
                                "entries": [{"rank": "1", "name": "Ciryl Gane"}],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        fighter = profile("Ciryl Gane")
        db.add(fighter)
        db.commit()

        rankings = load_rankings(db, rankings_path)

    entry = rankings["promotions"][0]["divisions"][0]["entries"][0]
    assert entry["fighter_id"] == fighter.id


def profile(name: str) -> FighterProfile:
    return FighterProfile(
        name=name,
        weight_class="Heavyweight",
        age=36,
        height_cm=193,
        reach_cm=206,
        wins=12,
        losses=2,
        ko_rate=0.3,
        submission_rate=0.4,
        takedown_accuracy=0.2,
        takedown_defense=0.5,
        strikes_landed_per_min=5.4,
        strikes_absorbed_per_min=2.2,
        source="test",
    )
