from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.data_jobs import DataImportSummary, run_data_import_cycle  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402

logger = logging.getLogger("mma.import_worker")
shutdown_requested = threading.Event()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scheduled MMA data imports.")
    parser.add_argument("--once", action="store_true", help="Run one import cycle and exit.")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=None,
        help="Seconds between import cycles. Defaults to DATA_IMPORT_INTERVAL_SECONDS.",
    )
    parser.add_argument(
        "--skip-initial-run",
        action="store_true",
        help="Wait one interval before the first import cycle.",
    )
    parser.add_argument(
        "--catalog-path",
        default=None,
        help="Optional source catalog path. Defaults to app/data/source_catalog.json.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    settings = get_settings()
    interval = max(args.interval_seconds or settings.data_import_interval_seconds, 60)
    run_on_startup = settings.data_import_run_on_startup and not args.skip_initial_run

    init_db()
    logger.info("import worker started interval_seconds=%s once=%s", interval, args.once)

    if args.once:
        run_once(args.catalog_path)
        return

    if not run_on_startup:
        wait_for_next_cycle(interval)

    while not shutdown_requested.is_set():
        run_once(args.catalog_path)
        wait_for_next_cycle(interval)

    logger.info("import worker stopped")


def run_once(catalog_path: str | None = None) -> DataImportSummary | None:
    started = time.monotonic()
    try:
        with SessionLocal() as db:
            summary = (
                run_data_import_cycle(db, catalog_path=catalog_path)
                if catalog_path
                else run_data_import_cycle(db)
            )
    except Exception:
        logger.exception("data import cycle failed")
        return None

    elapsed = time.monotonic() - started
    logger.info(
        "data import cycle completed seconds=%.2f records=%s features=%s promoted=%s "
        "current_fights=%s media_overrides=%s media_generated=%s media_found=%s "
        "media_verified=%s media_broken=%s fighters=%s external_features=%s",
        elapsed,
        summary.records_seen,
        summary.features_imported,
        summary.profiles_promoted,
        summary.current_fights_imported,
        summary.media_overrides_imported,
        summary.media_improvement["generated"],
        summary.media_improvement["wikimedia_found"],
        summary.media_improvement["verified"],
        summary.media_improvement["broken"],
        summary.fighters_in_db,
        summary.external_features_in_db,
    )
    return summary


def wait_for_next_cycle(interval: int) -> None:
    logger.info("next data import cycle in %s seconds", interval)
    shutdown_requested.wait(interval)


def request_shutdown(signum: int, frame: object) -> None:
    logger.info("received shutdown signal %s", signum)
    shutdown_requested.set()


if __name__ == "__main__":
    main()
