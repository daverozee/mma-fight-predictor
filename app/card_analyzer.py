from __future__ import annotations

import ast
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.prediction_agent import PredictionAgent, implied_probability
from app.media import thumbnail_urls_for_names
from app.models import FighterExternalFeature, FighterProfile

ODDS_SOURCE = "the-odds-api-mma-current"
ODDS_PREFIX = "the_odds_api_mma_current_"
UPCOMING_CARDS_PATH = Path(__file__).resolve().parent / "data" / "upcoming_cards.json"
CARD_WINDOW_HOURS = 12


def analyze_upcoming_cards(
    db: Session,
    prediction_agent: PredictionAgent,
    limit_cards: int = 8,
    now: datetime | None = None,
    catalog_path: Path = UPCOMING_CARDS_PATH,
) -> dict[str, object]:
    now = now or datetime.now(timezone.utc)
    events = upcoming_odds_events(db, now)
    catalog_cards = curated_cards(catalog_path, now)
    profiles = profiles_by_normalized_name(db, events, catalog_cards)
    thumbnails = thumbnail_urls_for_names(db, card_fighter_names(events, catalog_cards))
    odds_by_pair = {pair_key(event["home_team"], event["away_team"]): event for event in events}
    consumed_pairs: set[str] = set()

    cards = []
    for card in catalog_cards:
        card_payload = analyze_curated_card(
            db,
            prediction_agent,
            card,
            profiles,
            thumbnails,
            odds_by_pair,
            consumed_pairs,
        )
        cards.append(card_payload)

    if not catalog_cards:
        remaining_events = [
            event for event in events if pair_key(event["home_team"], event["away_team"]) not in consumed_pairs
        ]
        cards.extend(
            analyze_odds_card_group(db, prediction_agent, group, profiles, thumbnails)
            for group in grouped_odds_events(remaining_events)
        )
    cards = sorted(cards, key=lambda card: card["sort_time"])[:limit_cards]
    for card in cards:
        enrich_card_counts(card)

    return {
        "source": ODDS_SOURCE,
        "generated_at": now.isoformat(),
        "summary": {
            "cards": len(cards),
            "fights": sum(card["fight_count"] for card in cards),
            "predictions": sum(card["prediction_count"] for card in cards),
            "missing_profile_fights": sum(
                1
                for card in cards
                for fight in card["fights"]
                if fight["prediction_status"] != "ready"
            ),
        },
        "cards": [public_card(card) for card in cards],
    }


def upcoming_odds_events(db: Session, now: datetime) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    rows = db.scalars(
        select(FighterExternalFeature)
        .where(FighterExternalFeature.source == ODDS_SOURCE)
        .order_by(FighterExternalFeature.fighter_name, FighterExternalFeature.feature_name)
    ).all()
    for row in rows:
        event = grouped.setdefault(row.fighter_name, {"home_team": row.fighter_name})
        key = row.feature_name.removeprefix(ODDS_PREFIX)
        event[key] = row.numeric_value if row.numeric_value is not None else row.text_value

    events = []
    for event in grouped.values():
        commence_at = parse_datetime(str(event.get("commence_time") or ""))
        away_team = clean_name(event.get("away_team"))
        home_team = clean_name(event.get("home_team"))
        if commence_at is None or commence_at.date() < now.date() or not home_team or not away_team:
            continue
        events.append(
            {
                "id": str(event.get("id") or f"{home_team}-{away_team}-{commence_at.isoformat()}"),
                "home_team": home_team,
                "away_team": away_team,
                "commence_at": commence_at,
                "sport_title": str(event.get("sport_title") or "MMA"),
                "bookmakers": parse_bookmakers(event.get("bookmakers")),
            }
        )
    return sorted(events, key=lambda event: (event["commence_at"], event["home_team"]))


def analyze_card_fight(
    db: Session,
    prediction_agent: PredictionAgent,
    event: dict[str, Any],
    profiles: dict[str, FighterProfile],
    thumbnails: dict[str, str],
    order: int,
    label: str | None = None,
    weight_class: str | None = None,
) -> dict[str, object]:
    home = event["home_team"]
    away = event["away_team"]
    home_profile = profiles.get(normalize_name(home))
    away_profile = profiles.get(normalize_name(away))
    odds = fight_odds(event["bookmakers"], home, away)
    base = {
        "event_id": event["id"],
        "home_team": home,
        "away_team": away,
        "home_profile_id": home_profile.id if home_profile else None,
        "away_profile_id": away_profile.id if away_profile else None,
        "home_record": record_label(home_profile),
        "away_record": record_label(away_profile),
        "home_thumbnail": thumbnails.get(home),
        "away_thumbnail": thumbnails.get(away),
        "commence_time": event["commence_at"].isoformat(),
        "start_label": event["commence_at"].strftime("%I:%M %p UTC").lstrip("0"),
        "order": order,
        "label": label or f"Fight {order}",
        "weight_class": weight_class or "",
        "odds": odds,
    }
    if home_profile is None or away_profile is None:
        missing = [name for name, profile in ((home, home_profile), (away, away_profile)) if profile is None]
        return {
            **base,
            "prediction_status": "missing_profile",
            "missing_profiles": missing,
            "prediction": None,
            "agent": None,
        }

    analysis = prediction_agent.analyze(db, home_profile, away_profile, include_sentiment=False)
    return {
        **base,
        "prediction_status": "ready",
        "missing_profiles": [],
        "prediction": analysis["prediction"],
        "agent": analysis["agent"],
    }


def profiles_by_normalized_name(
    db: Session,
    events: list[dict[str, Any]],
    cards: list[dict[str, Any]] | None = None,
) -> dict[str, FighterProfile]:
    names = {event["home_team"] for event in events} | {event["away_team"] for event in events}
    for card in cards or []:
        for fight in card.get("fights", []):
            names.add(clean_name(fight.get("fighter_a")))
            names.add(clean_name(fight.get("fighter_b")))
    profiles = db.scalars(select(FighterProfile).where(FighterProfile.name.in_(names))).all()
    found = {normalize_name(profile.name): profile for profile in profiles}
    missing = {name for name in names if normalize_name(name) not in found}
    if missing:
        for profile in db.scalars(select(FighterProfile)).all():
            normalized = normalize_name(profile.name)
            if normalized in {normalize_name(name) for name in missing}:
                found[normalized] = profile
    return found


def analyze_curated_card(
    db: Session,
    prediction_agent: PredictionAgent,
    card: dict[str, Any],
    profiles: dict[str, FighterProfile],
    thumbnails: dict[str, str],
    odds_by_pair: dict[str, dict[str, Any]],
    consumed_pairs: set[str],
) -> dict[str, object]:
    fights = []
    card_date = parse_datetime(f"{card['date']}T23:00:00Z") or datetime.now(timezone.utc)
    for fight in sorted(card.get("fights", []), key=lambda item: int(item.get("order", 0)), reverse=True):
        fighter_a = clean_name(fight.get("fighter_a"))
        fighter_b = clean_name(fight.get("fighter_b"))
        key = pair_key(fighter_a, fighter_b)
        odds_event = odds_by_pair.get(key)
        event = {
            "id": f"{card['id']}-{key}",
            "home_team": fighter_a,
            "away_team": fighter_b,
            "commence_at": card_date,
            "sport_title": "MMA",
            "bookmakers": [],
        }
        if odds_event:
            event["id"] = odds_event["id"]
            event["commence_at"] = odds_event["commence_at"]
            event["sport_title"] = odds_event["sport_title"]
            event["bookmakers"] = odds_event["bookmakers"]
        consumed_pairs.add(key)
        fights.append(
            analyze_card_fight(
                db,
                prediction_agent,
                event,
                profiles,
                thumbnails,
                order=int(fight.get("order", 0)),
                label=str(fight.get("label") or ""),
                weight_class=str(fight.get("weight_class") or ""),
            )
        )
    return {
        "id": card["id"],
        "title": card["title"],
        "promotion": card.get("promotion", "MMA"),
        "date": card["date"],
        "date_label": card_date.strftime("%b %d, %Y"),
        "venue": card.get("venue", ""),
        "location": card.get("location", ""),
        "source_label": card.get("source_label", "Curated card"),
        "source_url": card.get("source_url"),
        "sort_time": card_date,
        "fights": fights,
    }


def analyze_odds_card_group(
    db: Session,
    prediction_agent: PredictionAgent,
    events: list[dict[str, Any]],
    profiles: dict[str, FighterProfile],
    thumbnails: dict[str, str],
) -> dict[str, object]:
    ordered = sorted(events, key=lambda event: event["commence_at"], reverse=True)
    first = min(event["commence_at"] for event in events)
    fights = [
        analyze_card_fight(
            db,
            prediction_agent,
            event,
            profiles,
            thumbnails,
            order=len(ordered) - index,
            label="Main Event" if index == 0 else f"Fight {len(ordered) - index}",
        )
        for index, event in enumerate(ordered)
    ]
    return {
        "id": f"odds-card-{first.date().isoformat()}-{normalize_name(ordered[0]['home_team'])}",
        "title": f"MMA Card - {first.strftime('%b %d, %Y')}",
        "promotion": "MMA",
        "date": first.date().isoformat(),
        "date_label": first.strftime("%b %d, %Y"),
        "venue": "",
        "location": "",
        "source_label": "Odds feed",
        "source_url": None,
        "sort_time": first,
        "fights": fights,
    }


def grouped_odds_events(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for event in sorted(events, key=lambda item: item["commence_at"]):
        if not groups:
            groups.append([event])
            continue
        previous_time = groups[-1][-1]["commence_at"]
        if event["commence_at"] - previous_time <= timedelta(hours=CARD_WINDOW_HOURS):
            groups[-1].append(event)
        else:
            groups.append([event])
    return groups


def enrich_card_counts(card: dict[str, Any]) -> None:
    fights = card["fights"]
    card["fight_count"] = len(fights)
    card["prediction_count"] = sum(1 for fight in fights if fight["prediction_status"] == "ready")
    card["main_event"] = next((fight for fight in fights if fight["label"] == "Main Event"), fights[0] if fights else None)


def public_card(card: dict[str, Any]) -> dict[str, object]:
    return {key: value for key, value in card.items() if key != "sort_time"}


def curated_cards(catalog_path: Path, now: datetime) -> list[dict[str, Any]]:
    if not catalog_path.exists():
        return []
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    cards = []
    for card in payload.get("cards", []):
        card_date = parse_datetime(f"{card.get('date')}T23:59:59Z")
        if card_date is not None and card_date.date() >= now.date():
            cards.append(card)
    return cards


def card_fighter_names(
    events: list[dict[str, Any]],
    cards: list[dict[str, Any]],
) -> list[str]:
    names = []
    for event in events:
        names.extend([event["home_team"], event["away_team"]])
    for card in cards:
        for fight in card.get("fights", []):
            names.extend([clean_name(fight.get("fighter_a")), clean_name(fight.get("fighter_b"))])
    return names


def fight_odds(bookmakers: list[dict[str, Any]], fighter_a: str, fighter_b: str) -> dict[str, object] | None:
    prices: dict[str, list[float]] = {normalize_name(fighter_a): [], normalize_name(fighter_b): []}
    books = set()
    for bookmaker in bookmakers:
        title = bookmaker.get("title") or bookmaker.get("key")
        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                name = normalize_name(str(outcome.get("name") or ""))
                if name in prices and isinstance(outcome.get("price"), int | float):
                    prices[name].append(float(outcome["price"]))
                    if title:
                        books.add(str(title))

    if not prices[normalize_name(fighter_a)] or not prices[normalize_name(fighter_b)]:
        return None
    average_a = round(sum(prices[normalize_name(fighter_a)]) / len(prices[normalize_name(fighter_a)]))
    average_b = round(sum(prices[normalize_name(fighter_b)]) / len(prices[normalize_name(fighter_b)]))
    return {
        "fighter_a": average_a,
        "fighter_b": average_b,
        "fighter_a_display": american_odds_label(average_a),
        "fighter_b_display": american_odds_label(average_b),
        "fighter_a_implied_probability": implied_probability(average_a),
        "fighter_b_implied_probability": implied_probability(average_b),
        "bookmakers": sorted(books),
        "bookmaker_count": len(books),
    }


def parse_bookmakers(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return []
    return parsed if isinstance(parsed, list) else []


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def clean_name(value: object) -> str:
    return str(value or "").strip()


def normalize_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def american_odds_label(value: int | float) -> str:
    return f"+{int(value)}" if value > 0 else str(int(value))


def pair_key(fighter_a: str, fighter_b: str) -> str:
    return "|".join(sorted([normalize_name(fighter_a), normalize_name(fighter_b)]))


def record_label(profile: FighterProfile | None) -> str:
    if profile is None:
        return ""
    return f"{profile.wins:.0f}-{profile.losses:.0f}"
