# Contributing

Thanks for helping improve MMA Fight Predictor. The project is early, so small, well-tested changes are especially welcome.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python scripts/train_model.py
uvicorn app.main:app --reload
```

## Before Opening a Pull Request

Run the local checks:

```powershell
ruff check .
pytest
```

## Data Contributions

Use reputable, permitted sources. Do not add data obtained in violation of website terms, paywall restrictions, API agreements, or privacy expectations. When adding a dataset or ingestion adapter, document:

- Source name and URL
- License or terms that allow use
- Collection date
- Field definitions
- Known missingness, bias, and leakage risks

## Modeling Contributions

Model changes should include a short explanation of the features used, the evaluation method, and how the change avoids future data leakage. This project should never present predictions as guaranteed results or betting advice.
