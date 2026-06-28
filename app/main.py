from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.auth import authenticate_user, create_user
from app.config import get_settings
from app.database import get_db, init_db
from app.fighters import (
    fighter_data_counts,
    get_fighter,
    list_fighters,
    list_imported_fighter_index,
    profile_to_features,
)
from app.ingestion.connectors import import_catalog, ingestion_counts
from app.ml.features import FighterFeatures
from app.ml.predictor import FightPredictor
from app.models import User

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    with next(get_db()) as db:
        counts = ingestion_counts(db)
        if counts["fighters"] == 0 or counts["external_features"] == 0:
            import_catalog(db)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
predictor = FightPredictor()


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db)
    if user is None:
        raise RedirectToLogin()
    return user


class RedirectToLogin(Exception):
    pass


@app.exception_handler(RedirectToLogin)
def redirect_to_login(request: Request, exc: RedirectToLogin) -> RedirectResponse:
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, user: User | None = Depends(current_user)) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"user": user})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "register.html", {"error": None})


@app.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    result = create_user(db, email, password)
    if result.error:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": result.error},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    request.session["user_id"] = result.user.id
    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    result = authenticate_user(db, email, password)
    if result.error:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": result.error},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    request.session["user_id"] = result.user.id
    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(require_user)) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})


@app.get("/fighters", response_class=HTMLResponse)
def fighters_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "fighters.html",
        {
            "user": user,
            "fighters": list_fighters(db),
            "imported_fighters": list_imported_fighter_index(db),
            "counts": fighter_data_counts(db),
        },
    )


@app.get("/predict", response_class=HTMLResponse)
def predict_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return render_predict_page(request, user, db)


@app.post("/predict", response_class=HTMLResponse)
def predict(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    a_name: str = Form(...),
    a_age: float = Form(...),
    a_height_cm: float = Form(...),
    a_reach_cm: float = Form(...),
    a_wins: float = Form(...),
    a_losses: float = Form(...),
    a_ko_rate: float = Form(...),
    a_submission_rate: float = Form(...),
    a_takedown_accuracy: float = Form(...),
    a_takedown_defense: float = Form(...),
    a_strikes_landed_per_min: float = Form(...),
    a_strikes_absorbed_per_min: float = Form(...),
    b_name: str = Form(...),
    b_age: float = Form(...),
    b_height_cm: float = Form(...),
    b_reach_cm: float = Form(...),
    b_wins: float = Form(...),
    b_losses: float = Form(...),
    b_ko_rate: float = Form(...),
    b_submission_rate: float = Form(...),
    b_takedown_accuracy: float = Form(...),
    b_takedown_defense: float = Form(...),
    b_strikes_landed_per_min: float = Form(...),
    b_strikes_absorbed_per_min: float = Form(...),
) -> HTMLResponse:
    try:
        fighter_a = FighterFeatures(
            name=a_name,
            age=a_age,
            height_cm=a_height_cm,
            reach_cm=a_reach_cm,
            wins=a_wins,
            losses=a_losses,
            ko_rate=a_ko_rate,
            submission_rate=a_submission_rate,
            takedown_accuracy=a_takedown_accuracy,
            takedown_defense=a_takedown_defense,
            strikes_landed_per_min=a_strikes_landed_per_min,
            strikes_absorbed_per_min=a_strikes_absorbed_per_min,
        )
        fighter_b = FighterFeatures(
            name=b_name,
            age=b_age,
            height_cm=b_height_cm,
            reach_cm=b_reach_cm,
            wins=b_wins,
            losses=b_losses,
            ko_rate=b_ko_rate,
            submission_rate=b_submission_rate,
            takedown_accuracy=b_takedown_accuracy,
            takedown_defense=b_takedown_defense,
            strikes_landed_per_min=b_strikes_landed_per_min,
            strikes_absorbed_per_min=b_strikes_absorbed_per_min,
        )
    except ValueError as exc:
        return render_predict_page(
            request,
            user,
            db,
            error=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    result = predictor.predict(fighter_a, fighter_b)
    return templates.TemplateResponse(
        request,
        "result.html",
        {"user": user, "fighter_a": fighter_a, "fighter_b": fighter_b, "result": result},
    )


@app.post("/predict/from-profiles", response_class=HTMLResponse)
def predict_from_profiles(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    a_profile_id: int = Form(...),
    b_profile_id: int = Form(...),
) -> HTMLResponse:
    if a_profile_id == b_profile_id:
        return render_predict_page(
            request,
            user,
            db,
            error="Choose two different fighter profiles.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    profile_a = get_fighter(db, a_profile_id)
    profile_b = get_fighter(db, b_profile_id)
    if profile_a is None or profile_b is None:
        return render_predict_page(
            request,
            user,
            db,
            error="One of those fighter profiles could not be found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    fighter_a = profile_to_features(profile_a)
    fighter_b = profile_to_features(profile_b)
    result = predictor.predict(fighter_a, fighter_b)
    return templates.TemplateResponse(
        request,
        "result.html",
        {"user": user, "fighter_a": fighter_a, "fighter_b": fighter_b, "result": result},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def render_predict_page(
    request: Request,
    user: User,
    db: Session,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "predict.html",
        {"user": user, "error": error, "fighters": list_fighters(db)},
        status_code=status_code,
    )
