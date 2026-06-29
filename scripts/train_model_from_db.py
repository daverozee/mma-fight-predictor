from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.ml.training import train_model_from_frame  # noqa: E402
from app.ml.training_data import build_training_frame_from_results  # noqa: E402


def main() -> None:
    settings = get_settings()
    model_path = Path(settings.model_path)
    report_path = model_path.with_suffix(".report.json")

    init_db()
    with SessionLocal() as db:
        training_frame = build_training_frame_from_results(db)

    if training_frame.empty:
        raise SystemExit("No profile-linked fight results are available for model training.")

    result = train_model_from_frame(training_frame, model_path, report_path)
    print(f"Training rows: {result.row_count}")
    print(f"Selected model: {result.selected_model}")
    for candidate in result.candidates:
        print(
            f"{candidate.name}: "
            f"accuracy={candidate.accuracy:.4f}, "
            f"balanced_accuracy={candidate.balanced_accuracy:.4f}, "
            f"log_loss={candidate.log_loss:.4f}, "
            f"roc_auc={candidate.roc_auc:.4f}"
        )
    print(f"Model written to {model_path}")
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
