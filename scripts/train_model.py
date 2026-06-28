from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.ml.training import train_model  # noqa: E402


def main() -> None:
    settings = get_settings()
    data_path = ROOT / "app" / "data" / "sample_fights.csv"
    train_model(data_path, settings.model_path)
    print(f"Model written to {settings.model_path}")


if __name__ == "__main__":
    main()
