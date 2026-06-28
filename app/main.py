from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, status
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
    promote_imported_fighters_to_profiles,
)
from app.fight_tree import build_defeat_tree, fight_result_count
from app.ingestion.connectors import import_catalog, ingestion_counts
from app.media import avatar_svg, fallback_thumbnail_url, fighter_thumbnail_urls, thumbnail_urls_for_names
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
        promote_imported_fighters_to_profiles(db)
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
def index(
    request: Request,
    user: User | None = Depends(current_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "counts": fighter_data_counts(db)},
    )


@app.get("/api-docs", response_class=HTMLResponse)
def api_docs(request: Request, user: User | None = Depends(current_user)) -> HTMLResponse:
    return templates.TemplateResponse(request, "api_docs.html", {"user": user})


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
    fighters = list_fighters(db)
    imported_fighters = list_imported_fighter_index(db)
    media_urls = fighter_thumbnail_urls(db, fighters)
    media_urls.update(thumbnail_urls_for_names(db, [fighter["name"] for fighter in imported_fighters]))
    return templates.TemplateResponse(
        request,
        "fighters.html",
        {
            "user": user,
            "fighters": fighters,
            "imported_fighters": imported_fighters,
            "counts": fighter_data_counts(db),
            "media_urls": media_urls,
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
        {
            "user": user,
            "fighter_a": fighter_a,
            "fighter_b": fighter_b,
            "fighter_a_thumbnail": fallback_thumbnail_url(fighter_a.name),
            "fighter_b_thumbnail": fallback_thumbnail_url(fighter_b.name),
            "result": result,
        },
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
    media_urls = fighter_thumbnail_urls(db, [profile_a, profile_b])
    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "user": user,
            "fighter_a": fighter_a,
            "fighter_b": fighter_b,
            "fighter_a_thumbnail": media_urls[profile_a.name],
            "fighter_b_thumbnail": media_urls[profile_b.name],
            "result": result,
        },
    )


@app.get("/tree", response_class=HTMLResponse)
def tree_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    fighter_id: int | None = Query(default=None),
) -> HTMLResponse:
    fighters = list_fighters(db)
    selected = get_fighter(db, fighter_id) if fighter_id else (fighters[0] if fighters else None)
    tree = build_defeat_tree(db, selected) if selected and fight_result_count(db) else None
    return templates.TemplateResponse(
        request,
        "tree.html",
        {
            "user": user,
            "fighters": fighters,
            "selected": selected,
            "tree": tree,
            "fight_result_count": fight_result_count(db),
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/fighter-thumbnail.svg")
def generated_fighter_thumbnail(name: str = Query(default="MMA Fighter", max_length=120)) -> Response:
    return Response(avatar_svg(name), media_type="image/svg+xml")


@app.get("/api/v1/meta")
def api_meta(db: Session = Depends(get_db)) -> dict[str, object]:
    counts = fighter_data_counts(db)
    return {
        "name": settings.app_name,
        "version": "v1",
        "counts": counts,
        "endpoints": {
            "fighters": "/api/v1/fighters",
            "fighter_detail": "/api/v1/fighters/{fighter_id}",
            "fighter_defeat_tree": "/api/v1/fighters/{fighter_id}/defeat-tree",
            "prediction": "/api/v1/predict",
        },
    }


@app.get("/api/v1/fighters")
def api_fighters(
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    fighters = list_fighters(db)
    if search:
        lowered = search.lower()
        fighters = [fighter for fighter in fighters if lowered in fighter.name.lower()]
    total = len(fighters)
    page = fighters[offset : offset + limit]
    media_urls = fighter_thumbnail_urls(db, page)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "fighters": [serialize_fighter(fighter, media_urls[fighter.name]) for fighter in page],
    }


@app.get("/api/v1/fighters/{fighter_id}")
def api_fighter(fighter_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    fighter = get_fighter(db, fighter_id)
    if fighter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fighter not found")
    media_urls = fighter_thumbnail_urls(db, [fighter])
    return serialize_fighter(fighter, media_urls[fighter.name])


@app.get("/api/v1/fighters/{fighter_id}/defeat-tree")
def api_fighter_defeat_tree(
    fighter_id: int,
    db: Session = Depends(get_db),
    depth: int = Query(default=4, ge=1, le=8),
    max_children: int = Query(default=80, ge=1, le=250),
) -> dict[str, object]:
    fighter = get_fighter(db, fighter_id)
    if fighter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fighter not found")
    return {
        "fighter": serialize_fighter(fighter, fighter_thumbnail_urls(db, [fighter])[fighter.name]),
        "fight_result_edges": fight_result_count(db),
        "tree": build_defeat_tree(db, fighter, depth=depth, max_children=max_children),
    }


@app.post("/api/v1/predict")
def api_predict(payload: dict[str, int], db: Session = Depends(get_db)) -> dict[str, object]:
    fighter_a_id = payload.get("fighter_a_id")
    fighter_b_id = payload.get("fighter_b_id")
    if fighter_a_id is None or fighter_b_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide fighter_a_id and fighter_b_id.",
        )
    if fighter_a_id == fighter_b_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose two different fighters.",
        )

    profile_a = get_fighter(db, fighter_a_id)
    profile_b = get_fighter(db, fighter_b_id)
    if profile_a is None or profile_b is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fighter not found")

    fighter_a = profile_to_features(profile_a)
    fighter_b = profile_to_features(profile_b)
    result = predictor.predict(fighter_a, fighter_b)
    media_urls = fighter_thumbnail_urls(db, [profile_a, profile_b])
    return {
        "fighter_a": serialize_fighter(profile_a, media_urls[profile_a.name]),
        "fighter_b": serialize_fighter(profile_b, media_urls[profile_b.name]),
        "prediction": result,
        "note": "Provisional-live-feed profiles may use league-average fallbacks for missing stats.",
    }


def render_predict_page(
    request: Request,
    user: User,
    db: Session,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    fighters = list_fighters(db)
    return templates.TemplateResponse(
        request,
        "predict.html",
        {
            "user": user,
            "error": error,
            "fighters": fighters,
            "media_urls": fighter_thumbnail_urls(db, fighters),
        },
        status_code=status_code,
    )


def serialize_fighter(fighter: object, thumbnail_url: str | None = None) -> dict[str, object]:
    return {
        "id": fighter.id,
        "name": fighter.name,
        "thumbnail_url": thumbnail_url or fallback_thumbnail_url(fighter.name),
        "weight_class": fighter.weight_class,
        "age": fighter.age,
        "height_cm": fighter.height_cm,
        "reach_cm": fighter.reach_cm,
        "wins": fighter.wins,
        "losses": fighter.losses,
        "ko_rate": fighter.ko_rate,
        "submission_rate": fighter.submission_rate,
        "takedown_accuracy": fighter.takedown_accuracy,
        "takedown_defense": fighter.takedown_defense,
        "strikes_landed_per_min": fighter.strikes_landed_per_min,
        "strikes_absorbed_per_min": fighter.strikes_absorbed_per_min,
        "source": fighter.source,
    }
