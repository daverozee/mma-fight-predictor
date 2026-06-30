from csv import DictReader
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ml.features import FighterFeatures
from app.models import FighterExternalFeature, FighterProfile
from app.social import normalize_instagram_url

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

AVERAGE_PROFILE_VALUES = {
    "age": 30.0,
    "height_cm": 176.0,
    "reach_cm": 180.0,
    "wins": 10.0,
    "losses": 3.0,
    "ko_rate": 0.34,
    "submission_rate": 0.22,
    "takedown_accuracy": 0.45,
    "takedown_defense": 0.69,
    "strikes_landed_per_min": 4.4,
    "strikes_absorbed_per_min": 3.4,
}

WEIGHT_CLASS_NAMES = {
    "SW": "Strawweight",
    "FLW": "Flyweight",
    "BW": "Bantamweight",
    "FW": "Featherweight",
    "LW": "Lightweight",
    "WW": "Welterweight",
    "MW": "Middleweight",
    "LHW": "Light Heavyweight",
    "HW": "Heavyweight",
}


def list_fighters(db: Session) -> list[FighterProfile]:
    return list(db.scalars(select(FighterProfile).order_by(FighterProfile.name)).all())


def search_fighters(
    db: Session,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[FighterProfile]]:
    query = select(FighterProfile)
    if search:
        query = query.where(FighterProfile.name.ilike(f"%{search.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    fighters = list(
        db.scalars(query.order_by(FighterProfile.name).offset(offset).limit(limit)).all()
    )
    return total, fighters


def list_imported_fighter_index(db: Session, limit: int = 250) -> list[dict[str, object]]:
    rows = db.execute(
        select(
            FighterExternalFeature.fighter_name,
            func.count(FighterExternalFeature.id).label("feature_count"),
            func.group_concat(func.distinct(FighterExternalFeature.source)).label("sources"),
        )
        .group_by(FighterExternalFeature.fighter_name)
        .order_by(FighterExternalFeature.fighter_name)
        .limit(limit)
    ).all()
    return [
        {
            "name": row.fighter_name,
            "feature_count": row.feature_count,
            "sources": sorted((row.sources or "").split(",")),
        }
        for row in rows
    ]


def fighter_data_counts(db: Session) -> dict[str, int]:
    return {
        "prediction_ready": db.scalar(select(func.count()).select_from(FighterProfile)) or 0,
        "imported_names": db.scalar(
            select(func.count(func.distinct(FighterExternalFeature.fighter_name)))
        )
        or 0,
        "external_features": db.scalar(select(func.count()).select_from(FighterExternalFeature)) or 0,
    }


def promote_imported_fighters_to_profiles(db: Session, limit: int | None = None) -> int:
    existing_profile_names = select(FighterProfile.name)
    imported_names = list(
        db.scalars(
            select(FighterExternalFeature.fighter_name)
            .where(FighterExternalFeature.fighter_name.not_in(existing_profile_names))
            .group_by(FighterExternalFeature.fighter_name)
            .order_by(FighterExternalFeature.fighter_name)
            .limit(limit)
        )
    )
    created = 0
    for name in imported_names:
        if db.scalar(select(FighterProfile.id).where(FighterProfile.name == name)) is not None:
            continue
        feature_map = features_for_fighter(db, name)
        profile = FighterProfile(**provisional_profile_payload(name, feature_map))
        db.add(profile)
        db.flush()
        db.query(FighterExternalFeature).filter(
            FighterExternalFeature.fighter_name == name,
            FighterExternalFeature.fighter_profile_id.is_(None),
        ).update({"fighter_profile_id": profile.id})
        created += 1
    db.commit()
    return created


def features_for_fighter(db: Session, name: str) -> dict[str, str | float]:
    rows = db.scalars(
        select(FighterExternalFeature).where(FighterExternalFeature.fighter_name == name)
    ).all()
    features = {}
    for row in rows:
        features[row.feature_name] = row.numeric_value if row.numeric_value is not None else row.text_value
    return features


def provisional_profile_payload(name: str, features: dict[str, str | float]) -> dict[str, str | float]:
    age = age_from_dob(features.get("balldontlie_fighters_live_date_of_birth"))
    height_cm = inches_to_cm(features.get("balldontlie_fighters_live_height_inches"))
    reach_cm = inches_to_cm(features.get("balldontlie_fighters_live_reach_inches"))
    weight_class = weight_class_name(features.get("balldontlie_fighters_live_weight_class_abbreviation"))
    wins = numeric_feature(features, "balldontlie_fighters_live_record_wins")
    losses = numeric_feature(features, "balldontlie_fighters_live_record_losses")

    return {
        "name": name,
        "weight_class": weight_class or "Unknown",
        "age": age or AVERAGE_PROFILE_VALUES["age"],
        "height_cm": height_cm or AVERAGE_PROFILE_VALUES["height_cm"],
        "reach_cm": reach_cm or height_cm or AVERAGE_PROFILE_VALUES["reach_cm"],
        "wins": wins if wins is not None else AVERAGE_PROFILE_VALUES["wins"],
        "losses": losses if losses is not None else AVERAGE_PROFILE_VALUES["losses"],
        "ko_rate": AVERAGE_PROFILE_VALUES["ko_rate"],
        "submission_rate": AVERAGE_PROFILE_VALUES["submission_rate"],
        "takedown_accuracy": AVERAGE_PROFILE_VALUES["takedown_accuracy"],
        "takedown_defense": AVERAGE_PROFILE_VALUES["takedown_defense"],
        "strikes_landed_per_min": AVERAGE_PROFILE_VALUES["strikes_landed_per_min"],
        "strikes_absorbed_per_min": AVERAGE_PROFILE_VALUES["strikes_absorbed_per_min"],
        "instagram_url": first_instagram_url(features),
        "source": "provisional-live-feed",
    }


def numeric_feature(features: dict[str, str | float], key: str) -> float | None:
    value = features.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def inches_to_cm(value: str | float | None) -> float | None:
    try:
        return round(float(value) * 2.54, 1) if value is not None else None
    except (TypeError, ValueError):
        return None


def age_from_dob(value: str | float | None) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        born = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    today = datetime.now(timezone.utc)
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return float(age)


def weight_class_name(value: str | float | None) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return WEIGHT_CLASS_NAMES.get(value.upper(), value)


def first_instagram_url(features: dict[str, str | float]) -> str | None:
    for key, value in features.items():
        if "instagram" in key.lower():
            url = normalize_instagram_url(value)
            if url:
                return url
    return None


def get_fighter(db: Session, fighter_id: int) -> FighterProfile | None:
    return db.get(FighterProfile, fighter_id)


def profile_to_features(profile: FighterProfile) -> FighterFeatures:
    return FighterFeatures(
        name=profile.name,
        weight_class=profile.weight_class,
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
    payload: dict[str, str | float] = {
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
    instagram_url = normalize_instagram_url(row.get("instagram_url") or row.get("instagram"))
    if instagram_url:
        payload["instagram_url"] = instagram_url
    return payload
