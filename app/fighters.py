from csv import DictReader
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.features import FighterFeatures
from app.models import FighterProfile

PROFILE_COLUMNS = [
    "name",
    "weight_class",
    "age",
    "height_cm",
    "reach_cm",
    "wins",
    "losses",
    "ko_rate",
    "submission_rate",
    "takedown_accuracy",
    "takedown_defense",
    "strikes_landed_per_min",
    "strikes_absorbed_per_min",
]


def list_fighters(db: Session) -> list[FighterProfile]:
    return list(db.scalars(select(FighterProfile).order_by(FighterProfile.name)).all())


def get_fighter(db: Session, fighter_id: int) -> FighterProfile | None:
    return db.get(FighterProfile, fighter_id)


def profile_to_features(profile: FighterProfile) -> FighterFeatures:
    return FighterFeatures(
        name=profile.name,
        age=profile.age,
        height_cm=profile.height_cm,
        reach_cm=profile.reach_cm,
        wins=profile.wins,
        losses=profile.losses,
        ko_rate=profile.ko_rate,
        submission_rate=profile.submission_rate,
        takedown_accuracy=profile.takedown_accuracy,
        takedown_defense=profile.takedown_defense,
        strikes_landed_per_min=profile.strikes_landed_per_min,
        strikes_absorbed_per_min=profile.strikes_absorbed_per_min,
    )


def import_fighter_profiles(db: Session, csv_path: str | Path, source: str = "csv") -> int:
    csv_path = Path(csv_path)
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(DictReader(file))

    imported = 0
    for row in rows:
        missing = set(PROFILE_COLUMNS) - set(row)
        if missing:
            raise ValueError(f"Fighter CSV is missing columns: {sorted(missing)}")

        payload = _row_to_payload(row, source)
        FighterFeatures(**{key: payload[key] for key in FighterFeatures.model_fields})
        profile = db.scalar(select(FighterProfile).where(FighterProfile.name == payload["name"]))
        if profile is None:
            profile = FighterProfile(**payload)
            db.add(profile)
        else:
            for key, value in payload.items():
                setattr(profile, key, value)
        imported += 1

    db.commit()
    return imported


def seed_sample_fighters(db: Session) -> int:
    if db.scalar(select(FighterProfile.id).limit(1)) is not None:
        return 0
    data_path = Path(__file__).resolve().parent / "data" / "sample_fighters.csv"
    return import_fighter_profiles(db, data_path, source="sample")


def _row_to_payload(row: dict[str, str], source: str) -> dict[str, str | float]:
    return {
        "name": row["name"].strip(),
        "weight_class": row["weight_class"].strip() or "Unknown",
        "age": float(row["age"]),
        "height_cm": float(row["height_cm"]),
        "reach_cm": float(row["reach_cm"]),
        "wins": float(row["wins"]),
        "losses": float(row["losses"]),
        "ko_rate": float(row["ko_rate"]),
        "submission_rate": float(row["submission_rate"]),
        "takedown_accuracy": float(row["takedown_accuracy"]),
        "takedown_defense": float(row["takedown_defense"]),
        "strikes_landed_per_min": float(row["strikes_landed_per_min"]),
        "strikes_absorbed_per_min": float(row["strikes_absorbed_per_min"]),
        "source": source,
    }
