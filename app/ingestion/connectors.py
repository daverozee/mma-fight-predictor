from __future__ import annotations

import csv
import json
import os
import re
import time
import urllib.request
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ml.features import FighterFeatures
from app.models import FighterExternalFeature, FighterProfile, SourceImportRun

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = ROOT / "app" / "data" / "source_catalog.json"

PROFILE_FIELDS = {
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
}
REQUIRED_PROFILE_FIELDS = PROFILE_FIELDS - {"weight_class"}


@dataclass(frozen=True)
class SourceResult:
    source_name: str
    records_seen: int
    profiles_created: int
    profiles_updated: int
    features_imported: int
    status: str
    error: str | None = None


@dataclass(frozen=True)
class CatalogResult:
    sources: list[SourceResult]

    @property
    def records_seen(self) -> int:
        return sum(source.records_seen for source in self.sources)

    @property
    def profiles_created(self) -> int:
        return sum(source.profiles_created for source in self.sources)

    @property
    def profiles_updated(self) -> int:
        return sum(source.profiles_updated for source in self.sources)

    @property
    def features_imported(self) -> int:
        return sum(source.features_imported for source in self.sources)


def import_catalog(db: Session, catalog_path: str | Path = DEFAULT_CATALOG_PATH) -> CatalogResult:
    catalog = load_catalog(catalog_path)
    results = []
    for source in catalog.get("sources", []):
        if source_enabled(source):
            results.append(import_source(db, source))
    return CatalogResult(sources=results)


def import_source(db: Session, source: dict[str, Any]) -> SourceResult:
    source_name = source["name"]
    source_format = source["format"].lower()
    source_location = source["location"]
    run = SourceImportRun(
        source_name=source_name,
        source_format=source_format,
        source_location=source_location,
    )
    db.add(run)
    db.commit()

    records_seen = profiles_created = profiles_updated = features_imported = 0
    try:
        records = read_records(source)
        for record in records:
            records_seen += 1
            profile, created, updated = upsert_profile(db, source, record)
            profiles_created += int(created)
            profiles_updated += int(updated)
            features_imported += upsert_external_features(db, source, record, profile)
        run.status = "completed"
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error = str(exc)
    finally:
        run.records_seen = records_seen
        run.profiles_created = profiles_created
        run.profiles_updated = profiles_updated
        run.features_imported = features_imported
        run.finished_at = datetime.utcnow()
        db.commit()

    return SourceResult(
        source_name=source_name,
        records_seen=records_seen,
        profiles_created=profiles_created,
        profiles_updated=profiles_updated,
        features_imported=features_imported,
        status=run.status,
        error=run.error,
    )


def load_catalog(catalog_path: str | Path) -> dict[str, Any]:
    path = resolve_location(str(catalog_path))
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_records(source: dict[str, Any]) -> list[dict[str, Any]]:
    source_format = source["format"].lower()
    records: list[dict[str, Any]] = []
    for body in read_source_bodies(source):
        if source_format == "csv":
            records.extend(list(csv.DictReader(body.splitlines())))
        elif source_format == "json":
            parsed = json.loads(body)
            raw_records = get_record_path(parsed, source.get("record_path"))
            if not isinstance(raw_records, list):
                raise ValueError(f"{source['name']} JSON record path did not resolve to a list")
            records.extend(flatten_record(record) for record in raw_records if isinstance(record, dict))
        else:
            raise ValueError(f"Unsupported source format: {source_format}")
    return records


def read_source_bodies(source: dict[str, Any]) -> list[str]:
    location = interpolate_env(source["location"])
    if not location.startswith(("http://", "https://")):
        return [resolve_location(location).read_text(encoding=source.get("encoding", "utf-8"))]

    pagination = source.get("pagination", {})
    if pagination.get("type") != "cursor":
        return [read_http_body(source, location)]

    bodies = []
    cursor: str | None = None
    max_pages = int(pagination.get("max_pages", 10))
    for _ in range(max_pages):
        page_url = with_query_params(
            location,
            {
                pagination.get("cursor_param", "cursor"): cursor,
                pagination.get("per_page_param", "per_page"): pagination.get("per_page"),
            },
        )
        body = read_http_body(source, page_url)
        bodies.append(body)
        parsed = json.loads(body)
        next_cursor = get_record_path(parsed, pagination.get("next_cursor_path", "meta.next_cursor"))
        if is_blank(next_cursor):
            break
        cursor = str(next_cursor)
    return bodies


def read_http_body(source: dict[str, Any], location: str) -> str:
    request = urllib.request.Request(location, headers=source_headers(source))
    max_retries = int(source.get("max_retries", 0))
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=int(source.get("timeout_seconds", 30))) as response:
                return response.read().decode(source.get("encoding", "utf-8"))
        except HTTPError as exc:
            if exc.code != 429 or attempt >= max_retries:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else int(source.get("retry_seconds", 65))
            time.sleep(delay)
    raise RuntimeError(f"Could not read {location}")


def source_headers(source: dict[str, Any]) -> dict[str, str]:
    headers = {"User-Agent": "mma-fight-predictor/0.1"}
    for key, value in source.get("headers", {}).items():
        headers[key] = interpolate_env(str(value))
    return headers


def upsert_profile(
    db: Session,
    source: dict[str, Any],
    record: dict[str, Any],
) -> tuple[FighterProfile | None, bool, bool]:
    payload = profile_payload(source, record)
    if not payload:
        return None, False, False

    FighterFeatures(**{key: payload[key] for key in FighterFeatures.model_fields})
    profile = db.scalar(select(FighterProfile).where(FighterProfile.name == payload["name"]))
    if profile is None:
        db.add(FighterProfile(**payload, source=source["name"]))
        db.flush()
        return db.scalar(select(FighterProfile).where(FighterProfile.name == payload["name"])), True, False

    changed = False
    for key, value in payload.items():
        if getattr(profile, key) != value:
            setattr(profile, key, value)
            changed = True
    if profile.source != source["name"]:
        profile.source = source["name"]
        changed = True
    db.flush()
    return profile, False, changed


def profile_payload(source: dict[str, Any], record: dict[str, Any]) -> dict[str, Any] | None:
    mapping = source.get("profile_mapping", {})
    defaults = source.get("profile_defaults", {})
    payload = {}
    for field in PROFILE_FIELDS:
        value = resolve_value(mapping.get(field), record)
        if is_blank(value) and field in defaults:
            value = defaults[field]
        if not is_blank(value):
            payload[field] = coerce_profile_value(field, value)

    if "name" in payload:
        payload["name"] = str(payload["name"]).strip()
    if "weight_class" not in payload:
        payload["weight_class"] = "Unknown"

    if not REQUIRED_PROFILE_FIELDS.issubset(payload):
        return None
    return payload


def upsert_external_features(
    db: Session,
    source: dict[str, Any],
    record: dict[str, Any],
    profile: FighterProfile | None,
) -> int:
    fighter_name = profile.name if profile is not None else resolve_value(source.get("profile_mapping", {}).get("name"), record)
    if is_blank(fighter_name):
        return 0

    used_fields = mapped_record_fields(source.get("profile_mapping", {}))
    feature_fields = selected_feature_fields(source, record, used_fields)
    imported = 0
    for raw_field in feature_fields:
        value = record.get(raw_field)
        if is_blank(value):
            continue
        feature_name = normalized_feature_name(source, raw_field)
        numeric_value, text_value = split_feature_value(value)
        existing = db.scalar(
            select(FighterExternalFeature).where(
                FighterExternalFeature.fighter_name == str(fighter_name).strip(),
                FighterExternalFeature.feature_name == feature_name,
                FighterExternalFeature.source == source["name"],
            )
        )
        if existing is None:
            db.add(
                FighterExternalFeature(
                    fighter_profile_id=profile.id if profile else None,
                    fighter_name=str(fighter_name).strip(),
                    feature_name=feature_name,
                    numeric_value=numeric_value,
                    text_value=text_value,
                    source=source["name"],
                    source_url=source["location"],
                    source_record_id=source_record_id(source, record),
                )
            )
        else:
            existing.fighter_profile_id = profile.id if profile else existing.fighter_profile_id
            existing.numeric_value = numeric_value
            existing.text_value = text_value
            existing.source_url = source["location"]
            existing.source_record_id = source_record_id(source, record)
            existing.imported_at = datetime.utcnow()
        imported += 1
    db.flush()
    return imported


def selected_feature_fields(
    source: dict[str, Any],
    record: dict[str, Any],
    used_fields: set[str],
) -> Iterable[str]:
    explicit_fields = source.get("feature_fields")
    if explicit_fields:
        return [field for field in explicit_fields if field in record]
    if source.get("extra_feature_mode") == "all_unmapped":
        return [field for field in record if field not in used_fields]
    return []


def mapped_record_fields(mapping: dict[str, Any]) -> set[str]:
    fields = set()
    for value in mapping.values():
        if isinstance(value, str):
            fields.add(value)
        elif isinstance(value, dict) and isinstance(value.get("field"), str):
            fields.add(value["field"])
    return fields


def resolve_value(spec: Any, record: dict[str, Any]) -> Any:
    if spec is None:
        return None
    if isinstance(spec, str):
        return record.get(spec)
    if isinstance(spec, dict):
        if "constant" in spec:
            return spec["constant"]
        if "field" in spec:
            return record.get(spec["field"])
    return None


def coerce_profile_value(field: str, value: Any) -> str | float:
    if field in {"name", "weight_class"}:
        return str(value).strip()
    return float(value)


def normalized_feature_name(source: dict[str, Any], field: str) -> str:
    prefix = source.get("feature_prefix") or source["name"]
    name = re.sub(r"[^a-zA-Z0-9]+", "_", f"{prefix}_{field}").strip("_").lower()
    return name[:160]


def split_feature_value(value: Any) -> tuple[float | None, str | None]:
    text = str(value).strip()
    try:
        return float(text), None
    except ValueError:
        return None, text


def source_record_id(source: dict[str, Any], record: dict[str, Any]) -> str | None:
    id_field = source.get("source_record_id_field")
    value = record.get(id_field) if id_field else None
    return None if is_blank(value) else str(value)


def get_record_path(parsed: Any, record_path: str | None) -> Any:
    current = parsed
    if not record_path:
        return current
    for segment in record_path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
    return current


def flatten_record(record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in record.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(flatten_record(value, path))
        else:
            flattened[path] = value
            if not prefix:
                flattened.setdefault(str(key), value)
    return flattened


def resolve_location(location: str) -> Path:
    path = Path(location)
    if path.is_absolute():
        return path
    return ROOT / path


def interpolate_env(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return os.getenv(match.group(1), "")

    return re.sub(r"\$\{([A-Z0-9_]+)\}", replace, value)


def source_enabled(source: dict[str, Any]) -> bool:
    if not source.get("enabled", True):
        return False
    enabled_env = source.get("enabled_env")
    if enabled_env and not os.getenv(enabled_env):
        return False
    return True


def with_query_params(location: str, params: dict[str, Any]) -> str:
    parsed = urlparse(location)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in params.items():
        if key and not is_blank(value):
            query[str(key)] = str(value)
    return urlunparse(parsed._replace(query=urlencode(query)))


def is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def ingestion_counts(db: Session) -> dict[str, int]:
    return {
        "fighters": db.scalar(select(func.count()).select_from(FighterProfile)) or 0,
        "external_features": db.scalar(select(func.count()).select_from(FighterExternalFeature)) or 0,
        "source_runs": db.scalar(select(func.count()).select_from(SourceImportRun)) or 0,
    }
