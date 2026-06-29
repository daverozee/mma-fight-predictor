from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
import argparse
import csv
import io
import sys
import urllib.request

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.fighters import AVERAGE_PROFILE_VALUES, fighter_data_counts  # noqa: E402
from app.models import FighterExternalFeature, FighterProfile  # noqa: E402


FIGHTER_URL = (
    "https://raw.githubusercontent.com/ThasankaK/UFC-Dataset-and-Model-Predictor/"
    "master/ufc_fighters.csv"
)
FIGHT_STATS_URL = (
    "https://raw.githubusercontent.com/ThasankaK/UFC-Dataset-and-Model-Predictor/"
    "master/ufc_event_fight_stats.csv"
)
FIGHTER_SOURCE = "ufcstats-fighter-career"
AGGREGATE_SOURCE = "ufcstats-fight-aggregates"


@dataclass
class FighterAggregate:
    name: str
    ufc_id: str
    bouts: int = 0
    wins: int = 0
    losses: int = 0
    age_total: float = 0.0
    latest_age: float | None = None
    height_cm: float | None = None
    fight_seconds: float = 0.0
    knockdowns: float = 0.0
    sig_strikes: float = 0.0
    sig_strike_attempts: float = 0.0
    total_strikes: float = 0.0
    total_strike_attempts: float = 0.0
    takedowns: float = 0.0
    takedown_attempts: float = 0.0
    submissions: float = 0.0
    reversals: float = 0.0
    control_seconds: float = 0.0
    strike_splits: dict[str, float] = field(default_factory=lambda: defaultdict(float))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import UFCStats career and fight features.")
    parser.add_argument("--fighters-url", default=FIGHTER_URL)
    parser.add_argument("--fight-stats-url", default=FIGHT_STATS_URL)
    parser.add_argument(
        "--skip-profile-update",
        action="store_true",
        help="Only import external features; do not update matching FighterProfile rows.",
    )
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        profiles = {profile.name: profile for profile in db.scalars(select(FighterProfile)).all()}
        feature_cache = {
            (feature.fighter_name, feature.feature_name, feature.source): feature
            for feature in db.scalars(
                select(FighterExternalFeature).where(
                    FighterExternalFeature.source.in_([FIGHTER_SOURCE, AGGREGATE_SOURCE])
                )
            ).all()
        }
        career_rows = list(csv.DictReader(open_text(args.fighters_url)))
        aggregate_rows = aggregate_fight_stats(args.fight_stats_url)

        career_features = 0
        aggregate_features = 0
        profiles_created = 0
        profiles_updated = 0

        for row in career_rows:
            name = text(row.get("fighter_name"))
            if not name:
                continue
            profile = profiles.get(name)
            if profile is None:
                profile = FighterProfile(**career_profile_payload(row))
                db.add(profile)
                db.flush()
                profiles[name] = profile
                profiles_created += 1
            career_features += upsert_features(
                db,
                fighter_name=name,
                profile_id=profile.id if profile else None,
                source=FIGHTER_SOURCE,
                source_url=args.fighters_url,
                source_record_id=text(row.get("fighter_id")),
                features=career_feature_payload(row),
                feature_cache=feature_cache,
            )
            if not args.skip_profile_update and profile is not None:
                profiles_updated += int(update_profile_from_career(profile, row))

        for aggregate in aggregate_rows.values():
            profile = profiles.get(aggregate.name)
            aggregate_features += upsert_features(
                db,
                fighter_name=aggregate.name,
                profile_id=profile.id if profile else None,
                source=AGGREGATE_SOURCE,
                source_url=args.fight_stats_url,
                source_record_id=aggregate.ufc_id,
                features=aggregate_feature_payload(aggregate),
                feature_cache=feature_cache,
            )
            if not args.skip_profile_update and profile is not None:
                profiles_updated += int(update_profile_from_aggregate(profile, aggregate))

        db.commit()
        counts = fighter_data_counts(db)

        print(f"Career feature rows processed: {len(career_rows)}")
        print(f"Career features upserted: {career_features}")
        print(f"Fight aggregate fighters processed: {len(aggregate_rows)}")
        print(f"Aggregate features upserted: {aggregate_features}")
        print(f"Profiles created: {profiles_created}")
        print(f"Profiles updated: {profiles_updated}")
    print(
        "Database totals: "
        f"fighters={counts['prediction_ready']}, "
        f"imported_names={counts['imported_names']}, "
        f"external_features={counts['external_features']}"
    )


def career_feature_payload(row: dict[str, str]) -> dict[str, str | float]:
    return {
        "ufcstats_fighter_id": text(row.get("fighter_id")),
        "ufcstats_url": text(row.get("fighter_url")),
        "date_of_birth": text(row.get("fighter_dob")),
        "height_cm": number(row.get("fighter_height_cm")),
        "weight_lbs": number(row.get("fighter_weight_lbs")),
        "reach_cm": number(row.get("fighter_reach_cm")),
        "stance": text(row.get("fighter_stance")),
        "career_wins": number(row.get("fighter_wins")),
        "career_losses": number(row.get("fighter_losses")),
        "career_draws": number(row.get("fighter_draws")),
        "strikes_landed_per_min": number(row.get("fighter_slpm")),
        "striking_accuracy": number(row.get("fighter_str_acc_%")),
        "strikes_absorbed_per_min": number(row.get("fighter_sapm")),
        "striking_defense": number(row.get("fighter_str_def_%")),
        "takedown_average": number(row.get("fighter_td_avg")),
        "takedown_accuracy": number(row.get("fighter_td_acc_%")),
        "takedown_defense": number(row.get("fighter_td_def_%")),
        "submission_average": number(row.get("fighter_sub_avg")),
    }


def career_profile_payload(row: dict[str, str]) -> dict[str, str | float]:
    height_cm = number(row.get("fighter_height_cm"))
    reach_cm = number(row.get("fighter_reach_cm"))
    wins = number(row.get("fighter_wins"))
    losses = number(row.get("fighter_losses"))
    return {
        "name": text(row.get("fighter_name")) or "Unknown fighter",
        "weight_class": weight_class_from_lbs(number(row.get("fighter_weight_lbs"))) or "Unknown",
        "age": model_safe_or_default("age", age_from_dob(text(row.get("fighter_dob")))),
        "height_cm": model_safe_or_default("height_cm", height_cm),
        "reach_cm": model_safe_or_default("reach_cm", reach_cm or height_cm),
        "wins": model_safe_or_default("wins", wins),
        "losses": model_safe_or_default("losses", losses),
        "ko_rate": AVERAGE_PROFILE_VALUES["ko_rate"],
        "submission_rate": AVERAGE_PROFILE_VALUES["submission_rate"],
        "takedown_accuracy": model_safe_or_default(
            "takedown_accuracy",
            number(row.get("fighter_td_acc_%")),
        ),
        "takedown_defense": model_safe_or_default(
            "takedown_defense",
            number(row.get("fighter_td_def_%")),
        ),
        "strikes_landed_per_min": model_safe_or_default(
            "strikes_landed_per_min",
            number(row.get("fighter_slpm")),
        ),
        "strikes_absorbed_per_min": model_safe_or_default(
            "strikes_absorbed_per_min",
            number(row.get("fighter_sapm")),
        ),
        "source": "ufcstats-enriched",
    }


def aggregate_fight_stats(location: str) -> dict[str, FighterAggregate]:
    aggregates: dict[str, FighterAggregate] = {}
    for row in csv.DictReader(open_text(location)):
        result = text(row.get("result"))
        for side, opponent_side in [("f1", "f2"), ("f2", "f1")]:
            fighter_id = text(row.get(f"{side}_id"))
            name = text(row.get(f"{side}_name"))
            if not fighter_id or not name:
                continue
            aggregate = aggregates.setdefault(
                fighter_id,
                FighterAggregate(name=name, ufc_id=fighter_id),
            )
            aggregate.bouts += 1
            opponent_id = text(row.get(f"{opponent_side}_id"))
            if result == fighter_id:
                aggregate.wins += 1
            elif result == opponent_id:
                aggregate.losses += 1

            add_fight_values(aggregate, row, side)
    return aggregates


def add_fight_values(aggregate: FighterAggregate, row: dict[str, str], side: str) -> None:
    age = number(row.get(f"{side}_age_during"))
    if age is not None:
        aggregate.age_total += age
        aggregate.latest_age = max(aggregate.latest_age or age, age)
    height = number(row.get(f"{side}_height_cm"))
    if height is not None:
        aggregate.height_cm = height

    fight_seconds = number(row.get(f"{side}_total_fight_time")) or 0.0
    aggregate.fight_seconds += fight_seconds
    aggregate.knockdowns += number(row.get(f"{side}_knockdowns")) or 0.0
    aggregate.sig_strikes += number(row.get(f"{side}_sig_strikes")) or 0.0
    aggregate.sig_strike_attempts += number(row.get(f"{side}_sig_strike_atts")) or 0.0
    aggregate.total_strikes += number(row.get(f"{side}_tot_strikes")) or 0.0
    aggregate.total_strike_attempts += number(row.get(f"{side}_tot_strike_atts")) or 0.0
    aggregate.takedowns += number(row.get(f"{side}_takedowns")) or 0.0
    aggregate.takedown_attempts += number(row.get(f"{side}_takedown_atts")) or 0.0
    aggregate.submissions += number(row.get(f"{side}_submissions")) or 0.0
    aggregate.reversals += number(row.get(f"{side}_reversals")) or 0.0
    aggregate.control_seconds += number(row.get(f"{side}_ctrl_time")) or 0.0
    split_fields = {
        "head": ("head_strikes", "head_strike_atts"),
        "body": ("body_strikes", "body_strike_atts"),
        "leg": ("leg_strikes", "leg_strike_atts"),
        "distance": ("dist_strikes", "dist_strike_atts"),
        "clinch": ("clinchs", "clinch_atts"),
        "ground": ("grounds", "ground_atts"),
    }
    for split, (landed_column, attempted_column) in split_fields.items():
        aggregate.strike_splits[f"{split}_strikes"] += (
            number(row.get(f"{side}_{landed_column}")) or 0.0
        )
        aggregate.strike_splits[f"{split}_attempts"] += (
            number(row.get(f"{side}_{attempted_column}")) or 0.0
        )


def aggregate_feature_payload(aggregate: FighterAggregate) -> dict[str, float | str]:
    bouts = max(aggregate.bouts, 1)
    fight_minutes = max(aggregate.fight_seconds / 60, 1)
    features: dict[str, float | str] = {
        "ufcstats_fighter_id": aggregate.ufc_id,
        "bouts_seen": float(aggregate.bouts),
        "wins_seen": float(aggregate.wins),
        "losses_seen": float(aggregate.losses),
        "win_rate_seen": safe_ratio(aggregate.wins, aggregate.wins + aggregate.losses),
        "average_age_during_bouts": aggregate.age_total / bouts,
        "latest_age_seen": aggregate.latest_age,
        "height_cm_seen": aggregate.height_cm,
        "average_fight_minutes": aggregate.fight_seconds / 60 / bouts,
        "knockdowns_per_fight": aggregate.knockdowns / bouts,
        "sig_strikes_per_minute_seen": aggregate.sig_strikes / fight_minutes,
        "sig_strike_attempts_per_minute_seen": aggregate.sig_strike_attempts / fight_minutes,
        "sig_strike_accuracy_seen": safe_ratio(
            aggregate.sig_strikes,
            aggregate.sig_strike_attempts,
        ),
        "total_strikes_per_minute_seen": aggregate.total_strikes / fight_minutes,
        "total_strike_accuracy_seen": safe_ratio(
            aggregate.total_strikes,
            aggregate.total_strike_attempts,
        ),
        "takedowns_per_fight": aggregate.takedowns / bouts,
        "takedown_accuracy_seen": safe_ratio(aggregate.takedowns, aggregate.takedown_attempts),
        "submission_attempts_per_fight": aggregate.submissions / bouts,
        "reversals_per_fight": aggregate.reversals / bouts,
        "control_seconds_per_fight": aggregate.control_seconds / bouts,
    }
    for key, value in aggregate.strike_splits.items():
        features[f"{key}_per_fight"] = value / bouts
    return features


def update_profile_from_career(profile: FighterProfile, row: dict[str, str]) -> bool:
    updates = {
        "age": age_from_dob(text(row.get("fighter_dob"))),
        "height_cm": number(row.get("fighter_height_cm")),
        "reach_cm": number(row.get("fighter_reach_cm")),
        "wins": number(row.get("fighter_wins")),
        "losses": number(row.get("fighter_losses")),
        "takedown_accuracy": number(row.get("fighter_td_acc_%")),
        "takedown_defense": number(row.get("fighter_td_def_%")),
        "strikes_landed_per_min": number(row.get("fighter_slpm")),
        "strikes_absorbed_per_min": number(row.get("fighter_sapm")),
    }
    weight_class = weight_class_from_lbs(number(row.get("fighter_weight_lbs")))
    if weight_class:
        updates["weight_class"] = weight_class
    return apply_profile_updates(profile, updates)


def update_profile_from_aggregate(profile: FighterProfile, aggregate: FighterAggregate) -> bool:
    features = aggregate_feature_payload(aggregate)
    updates = {
        "height_cm": features.get("height_cm_seen"),
        "ko_rate": min(float(features["knockdowns_per_fight"]), 1.0),
        "submission_rate": min(float(features["submission_attempts_per_fight"]), 1.0),
        "takedown_accuracy": features.get("takedown_accuracy_seen"),
        "strikes_landed_per_min": features.get("sig_strikes_per_minute_seen"),
    }
    return apply_profile_updates(profile, updates)


def apply_profile_updates(profile: FighterProfile, updates: dict[str, float | str | None]) -> bool:
    changed = False
    for field_name, value in updates.items():
        if value is None or value == "":
            continue
        if field_name in {
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
        }:
            value = model_safe_number(field_name, float(value))
        if getattr(profile, field_name) != value:
            setattr(profile, field_name, value)
            changed = True
    if changed and profile.source != "ufcstats-enriched":
        profile.source = "ufcstats-enriched"
    return changed


def upsert_features(
    db,
    fighter_name: str,
    profile_id: int | None,
    source: str,
    source_url: str,
    source_record_id: str | None,
    features: dict[str, str | float | None],
    feature_cache: dict[tuple[str, str, str], FighterExternalFeature],
) -> int:
    imported = 0
    for feature_name, value in features.items():
        if value is None or value == "":
            continue
        numeric_value = value if isinstance(value, (float, int)) else None
        text_value = None if numeric_value is not None else str(value)
        feature_key = (fighter_name, feature_name, source)
        existing = feature_cache.get(feature_key)
        if existing is None:
            existing = FighterExternalFeature(
                fighter_profile_id=profile_id,
                fighter_name=fighter_name,
                feature_name=feature_name,
                numeric_value=float(numeric_value) if numeric_value is not None else None,
                text_value=text_value,
                source=source,
                source_url=source_url,
                source_record_id=source_record_id,
            )
            db.add(existing)
            feature_cache[feature_key] = existing
        else:
            existing.fighter_profile_id = profile_id or existing.fighter_profile_id
            existing.numeric_value = float(numeric_value) if numeric_value is not None else None
            existing.text_value = text_value
            existing.source_url = source_url
            existing.source_record_id = source_record_id
            existing.imported_at = datetime.utcnow()
        imported += 1
    return imported


def open_text(location: str):
    if location.startswith(("http://", "https://")):
        with urllib.request.urlopen(location, timeout=60) as response:
            text_body = response.read().decode("utf-8", errors="replace")
        return io.StringIO(text_body)
    return Path(location).open("r", encoding="utf-8")


def text(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def number(value: str | None) -> float | None:
    value = text(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def age_from_dob(value: str | None) -> float | None:
    if not value:
        return None
    try:
        born = date.fromisoformat(value)
    except ValueError:
        return None
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return float(min(max(age, 18), 60))


def weight_class_from_lbs(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= 115:
        return "Strawweight"
    if value <= 125:
        return "Flyweight"
    if value <= 135:
        return "Bantamweight"
    if value <= 145:
        return "Featherweight"
    if value <= 155:
        return "Lightweight"
    if value <= 170:
        return "Welterweight"
    if value <= 185:
        return "Middleweight"
    if value <= 205:
        return "Light Heavyweight"
    return "Heavyweight"


def model_safe_number(field_name: str, value: float) -> float:
    limits = {
        "age": (18, 60),
        "height_cm": (140, 230),
        "reach_cm": (140, 230),
        "wins": (0, 100),
        "losses": (0, 100),
        "ko_rate": (0, 1),
        "submission_rate": (0, 1),
        "takedown_accuracy": (0, 1),
        "takedown_defense": (0, 1),
        "strikes_landed_per_min": (0, 15),
        "strikes_absorbed_per_min": (0, 15),
    }
    minimum, maximum = limits[field_name]
    return round(min(max(value, minimum), maximum), 3)


def model_safe_or_default(field_name: str, value: float | None) -> float:
    if value is None:
        return AVERAGE_PROFILE_VALUES[field_name]
    return model_safe_number(field_name, value)


if __name__ == "__main__":
    main()
