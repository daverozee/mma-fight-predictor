from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.ml.backtesting import chronological_backtest, write_backtest_report  # noqa: E402
from app.ml.training_data import build_training_frame_from_results  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a chronological MMA prediction backtest.")
    parser.add_argument(
        "--cutoff-date",
        default=None,
        help="First test date in YYYY-MM-DD format. Defaults to an 80/20 chronological split.",
    )
    parser.add_argument(
        "--train-fraction",
        type=float,
        default=0.8,
        help="Chronological train fraction when --cutoff-date is omitted.",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help="Where to write the JSON report. Defaults to storage/model.backtest.json.",
    )
    args = parser.parse_args()

    settings = get_settings()
    report_path = Path(args.report_path) if args.report_path else Path(settings.model_path).with_suffix(
        ".backtest.json"
    )

    init_db()
    with SessionLocal() as db:
        frame = build_training_frame_from_results(db)
    if frame.empty:
        raise SystemExit("No profile-linked fight results are available for backtesting.")

    result = chronological_backtest(
        frame,
        cutoff_date=args.cutoff_date,
        train_fraction=args.train_fraction,
    )
    write_backtest_report(result, report_path)

    print(f"Cutoff date: {result.cutoff_date}")
    print(f"Training fights: {result.train_fights}")
    print(f"Test fights: {result.test_fights}")
    print(f"Selected model: {result.selected_model}")
    print(f"Accuracy: {result.accuracy:.4f}")
    print(f"Balanced accuracy: {result.balanced_accuracy:.4f}")
    print(f"Log loss: {result.log_loss:.4f}")
    print(f"ROC AUC: {result.roc_auc:.4f}")
    print(f"Brier score: {result.brier_score:.4f}")
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
