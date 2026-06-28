from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.fighters import fighter_data_counts, promote_imported_fighters_to_profiles  # noqa: E402


def main() -> None:
    init_db()
    with SessionLocal() as db:
        created = promote_imported_fighters_to_profiles(db)
        counts = fighter_data_counts(db)
    print(
        f"Promoted profiles: {created}; "
        f"prediction_ready={counts['prediction_ready']}; "
        f"imported_names={counts['imported_names']}; "
        f"external_features={counts['external_features']}"
    )


if __name__ == "__main__":
    main()
