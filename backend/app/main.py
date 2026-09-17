from __future__ import annotations

from datetime import date, datetime, timezone
from datetime import timedelta
from decimal import Decimal
from enum import Enum
import os
import logging
from urllib.parse import urlencode, quote
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


DATABASE_PATH = Path(__file__).resolve().parents[1] / "promise_tracker.db"
logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")
APP_ENV = os.getenv("APP_ENV", "development")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
API_URL = os.getenv("API_URL", "http://localhost:8000")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-only-secret")

# Render exposes Postgres URLs with the postgres:// scheme. SQLAlchemy uses the
# explicit psycopg driver scheme that is installed by requirements.txt.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine_options: dict = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class SpaceType(str, Enum):
    PERSONAL = "personal"
    GROUP = "group"


class PromiseStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TrackingMode(str, Enum):
    CHECK_OFF = "check_off"
    QUANTITY = "quantity"
    DURATION = "duration"
    CUMULATIVE = "cumulative"
    PERCENTAGE = "percentage"
    CUSTOM = "custom"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Space(Base):
    __tablename__ = "spaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(20))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Group(Base):
    __tablename__ = "groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    space_id: Mapped[str] = mapped_column(ForeignKey("spaces.id"), unique=True)
    join_policy: Mapped[str] = mapped_column(String(30), default="invite_link")
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Kolkata")


class Membership(Base):
    __tablename__ = "group_memberships"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20), default="member")
    user: Mapped[User] = relationship()


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id"), index=True)
    token: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class JoinRequest(Base):
    __tablename__ = "join_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    user: Mapped[User] = relationship()


class Promise(Base):
    __tablename__ = "promises"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    space_id: Mapped[str] = mapped_column(ForeignKey("spaces.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(60), default="Personal")
    tracking_mode: Mapped[str] = mapped_column(String(30))
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    schedule_type: Mapped[str] = mapped_column(String(20), default="recurring")
    frequency: Mapped[str] = mapped_column(String(40), default="daily")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=PromiseStatus.ACTIVE.value)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    why_it_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    owner: Mapped[User] = relationship()
    progress_entries: Mapped[list["ProgressEntry"]] = relationship(cascade="all, delete-orphan")


class ProgressEntry(Base):
    __tablename__ = "progress_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    promise_id: Mapped[str] = mapped_column(ForeignKey("promises.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("1"))
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PromiseCreate(BaseModel):
    title: str = Field(min_length=5, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    category: str = Field(default="Personal", min_length=1, max_length=60)
    tracking_mode: TrackingMode
    unit: str | None = Field(default=None, max_length=30)
    target_value: Decimal | None = Field(default=None, gt=0)
    schedule_type: str = Field(default="recurring", pattern="^(recurring|date_range)$")
    frequency: str = Field(default="daily", max_length=40)
    start_date: date | None = None
    end_date: date | None = None
    why_it_matters: str | None = Field(default=None, max_length=500)

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Title must contain at least 5 characters")
        return value


class ProgressCreate(BaseModel):
    value: Decimal = Field(default=Decimal("1"), gt=0)
    note: str | None = Field(default=None, max_length=300)


class GroupCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    join_policy: str = Field(default="invite_link", pattern="^(invite_link|admin_approval)$")
    timezone: str = Field(default="Asia/Kolkata", max_length=80)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Group name must contain at least 3 characters")
        return value


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    join_policy: str | None = Field(default=None, pattern="^(invite_link|admin_approval)$")
    timezone: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Group name must contain at least 3 characters")
        return value


class PromiseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=80)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    frequency: str | None = Field(default=None, min_length=1, max_length=40)
    target_value: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=30)
    why_it_matters: str | None = Field(default=None, max_length=500)


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)

    @field_validator("display_name")
    @classmethod
    def trim_display_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Display name must contain at least 2 characters")
        return value


def group_membership_or_403(group_id: str, user_id: str, db: Session) -> Membership:
    membership = db.query(Membership).filter_by(group_id=group_id, user_id=user_id).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="You are not a group member")
    return membership


def recurring_period_start(frequency: str, today: date | None = None) -> date:
    today = today or datetime.now(timezone.utc).date()
    if frequency == "weekly":
        return today - timedelta(days=today.weekday())
    if frequency == "monthly":
        return today.replace(day=1)
    return today


def progress_for_current_period(promise: Promise) -> list[ProgressEntry]:
    if promise.schedule_type != "recurring":
        return list(promise.progress_entries)
    start = recurring_period_start(promise.frequency)
    return [entry for entry in promise.progress_entries if entry.completed_at.date() >= start]


class PromiseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    category: str
    tracking_mode: str
    unit: str | None
    target_value: Decimal | None
    schedule_type: str
    frequency: str
    status: str
    is_locked: bool
    current_progress: Decimal
    completion_percent: int
    owner_name: str
    why_it_matters: str | None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def development_user(db: Session) -> User:
    user = db.get(User, "demo-user")
    if user is None:
        user = User(id="demo-user", email="you@example.com", display_name="You")
        db.add(user)
        db.flush()
        db.add(Space(id="personal-demo", name="My promises", type=SpaceType.PERSONAL.value, owner_id=user.id))
        db.commit()
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("promise_session")
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token:
        try:
            claims = jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
            user = db.get(User, claims.get("sub"))
            if user:
                return user
        except JWTError:
            pass
    if APP_ENV != "production":
        return development_user(db)
    raise HTTPException(status_code=401, detail="Sign in with Google to continue")


def promise_view(promise: Promise) -> PromiseResponse:
    progress = sum((entry.value for entry in progress_for_current_period(promise)), Decimal("0"))
    if promise.tracking_mode == TrackingMode.CHECK_OFF.value:
        progress = Decimal("1") if progress else Decimal("0")
    target = promise.target_value or Decimal("1")
    percent = min(100, int((progress / target) * 100)) if target else 0
    return PromiseResponse(
        id=promise.id, title=promise.title, category=promise.category,
        tracking_mode=promise.tracking_mode, unit=promise.unit, target_value=promise.target_value,
        schedule_type=promise.schedule_type, frequency=promise.frequency, status=promise.status,
        is_locked=promise.is_locked, current_progress=progress, completion_percent=percent,
        owner_name=promise.owner.display_name, why_it_matters=promise.why_it_matters,
    )


def ensure_space_access(space_id: str, user: User, db: Session) -> Space:
    space = db.get(Space, space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")
    if space.type == SpaceType.PERSONAL.value and space.owner_id != user.id:
        raise HTTPException(status_code=403, detail="This personal space is private")
    if space.type == SpaceType.GROUP.value:
        group = db.query(Group).filter_by(space_id=space.id).first()
        membership = db.query(Membership).filter_by(group_id=group.id, user_id=user.id).first()
        if membership is None:
            raise HTTPException(status_code=403, detail="You are not a group member")
    return space


def get_promise_or_404(promise_id: str, db: Session) -> Promise:
    promise = db.get(Promise, promise_id)
    if promise is None:
        raise HTTPException(status_code=404, detail="Promise not found")
    return promise


Base.metadata.create_all(engine)

app = FastAPI(title="Promise Tracker API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://puneeee.github.io",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


def safe_frontend_destination(next_url: str | None) -> str:
    """Only redirect OAuth users back to this application's configured frontend."""
    if next_url and next_url.startswith(FRONTEND_URL.rstrip("/")):
        return next_url
    return FRONTEND_URL


def frontend_session_destination(next_url: str | None, token: str) -> str:
    """Use a URL fragment so the browser, not intermediary servers, receives the token."""
    destination = safe_frontend_destination(next_url).split("#", 1)[0]
    return f"{destination}#session={quote(token, safe='')}"


@app.get("/auth/google/login")
def google_login(next: str | None = None):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or APP_ENV != "production":
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    state = jwt.encode(
        {"purpose": "google-oauth", "next": safe_frontend_destination(next), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        SESSION_SECRET,
        algorithm="HS256",
    )
    params = urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{API_URL}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@app.get("/auth/google/callback")
async def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        claims = jwt.decode(state, SESSION_SECRET, algorithms=["HS256"])
        if claims.get("purpose") != "google-oauth":
            raise JWTError("Invalid OAuth state")
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="Google sign-in session expired; please try again") from exc
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            exchange = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": f"{API_URL}/auth/google/callback",
                "grant_type": "authorization_code",
            })
            if exchange.is_error:
                logger.warning("Google token exchange failed: status=%s body=%s", exchange.status_code, exchange.text)
                raise HTTPException(status_code=401, detail="Google could not complete sign-in")
            id_token = exchange.json().get("id_token")
            verified = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token})
            if verified.is_error:
                logger.warning("Google ID-token verification failed: status=%s body=%s", verified.status_code, verified.text)
                raise HTTPException(status_code=401, detail="Google identity verification failed")
            identity = verified.json()
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        logger.exception("Google OAuth network request failed")
        raise HTTPException(status_code=502, detail="Could not reach Google sign-in. Please try again.") from exc
    if identity.get("aud") != GOOGLE_CLIENT_ID or identity.get("email_verified") not in {"true", True}:
        raise HTTPException(status_code=401, detail="Google identity verification failed")
    email = identity["email"].lower()
    try:
        user = db.query(User).filter_by(email=email).first()
        if user is None:
            user = User(id=str(uuid4()), email=email, display_name=identity.get("name") or email.split("@")[0])
            db.add(user)
            # Space.owner_id is a foreign key. Flush the user first because these
            # two independent model instances do not have an ORM relationship.
            db.flush()
            db.add(Space(id=str(uuid4()), name="My promises", type=SpaceType.PERSONAL.value, owner_id=user.id))
            db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not create or load Google OAuth user")
        raise HTTPException(status_code=500, detail="Could not set up your account. Please try again.") from exc
    session_token = jwt.encode(
        {"sub": user.id, "exp": datetime.now(timezone.utc) + timedelta(days=7)},
        SESSION_SECRET,
        algorithm="HS256",
    )
    response = RedirectResponse(frontend_session_destination(claims.get("next"), session_token))
    response.set_cookie(
        key="promise_session", value=session_token, httponly=True, secure=True,
        samesite="none", max_age=7 * 24 * 60 * 60,
    )
    return response


@app.api_route("/auth/logout", methods=["GET", "POST"])
def logout(next: str | None = None):
    response = RedirectResponse(safe_frontend_destination(next), status_code=303)
    response.delete_cookie("promise_session", secure=True, samesite="none")
    return response


@app.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(current_user)):
    personal_space = (
        db.query(Space)
        .filter_by(owner_id=user.id, type=SpaceType.PERSONAL.value)
        .first()
    )
    if personal_space is None:
        raise HTTPException(status_code=500, detail="Your personal space could not be found")
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "personal_space_id": personal_space.id,
    }


@app.patch("/me")
def update_me(payload: ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    user.display_name = payload.display_name
    db.commit()
    return {"id": user.id, "email": user.email, "display_name": user.display_name}


@app.get("/spaces/{space_id}/promises", response_model=list[PromiseResponse])
def list_promises(space_id: str, view: str = "active", db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_space_access(space_id, user, db)
    if view not in {"active", "completed", "archived", "all"}:
        raise HTTPException(status_code=422, detail="Unknown promise view")
    query = db.query(Promise).filter_by(space_id=space_id)
    if view != "all":
        query = query.filter_by(status=view)
    promises = query.order_by(Promise.created_at.desc()).all()
    return [promise_view(promise) for promise in promises]


@app.post("/spaces/{space_id}/promises", response_model=PromiseResponse, status_code=status.HTTP_201_CREATED)
def create_promise(payload: PromiseCreate, space_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_space_access(space_id, user, db)
    if payload.schedule_type == "date_range" and (not payload.start_date or not payload.end_date or payload.end_date < payload.start_date):
        raise HTTPException(status_code=422, detail="A date-range promise needs a valid start and end date")
    if payload.tracking_mode != TrackingMode.CHECK_OFF and payload.target_value is None:
        raise HTTPException(status_code=422, detail="A target value is required for this tracking mode")
    if payload.tracking_mode != TrackingMode.CHECK_OFF and not (payload.unit or "").strip():
        raise HTTPException(status_code=422, detail="A unit is required for this tracking mode")
    promise = Promise(id=str(uuid4()), space_id=space_id, owner_id=user.id, **payload.model_dump())
    db.add(promise)
    db.commit()
    db.refresh(promise)
    return promise_view(promise)


@app.post("/promises/{promise_id}/progress", response_model=PromiseResponse)
def add_progress(promise_id: str, payload: ProgressCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    promise = get_promise_or_404(promise_id, db)
    ensure_space_access(promise.space_id, user, db)
    if promise.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the promise owner can update progress")
    if promise.status == PromiseStatus.ARCHIVED.value or promise.is_locked:
        raise HTTPException(status_code=409, detail="This promise cannot receive progress updates")
    if promise.schedule_type == "recurring" and promise.tracking_mode == TrackingMode.CHECK_OFF.value:
        if progress_for_current_period(promise):
            raise HTTPException(status_code=409, detail="This promise is already complete for the current period")
    db.add(ProgressEntry(id=str(uuid4()), promise_id=promise.id, owner_id=user.id, value=payload.value, note=payload.note))
    db.flush()
    current = sum((entry.value for entry in progress_for_current_period(promise)), Decimal("0"))
    if promise.schedule_type == "date_range" and promise.target_value and current >= promise.target_value:
        promise.status = PromiseStatus.COMPLETED.value
    db.commit()
    db.refresh(promise)
    return promise_view(promise)


@app.get("/promises/{promise_id}/history")
def promise_history(promise_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    promise = get_promise_or_404(promise_id, db)
    ensure_space_access(promise.space_id, user, db)
    entries = (
        db.query(ProgressEntry)
        .filter_by(promise_id=promise.id)
        .order_by(ProgressEntry.completed_at.asc())
        .all()
    )
    total = Decimal("0")
    period_total = Decimal("0")
    period_start = recurring_period_start(promise.frequency) if promise.schedule_type == "recurring" else None
    result = []
    for entry in entries:
        total += entry.value
        in_current_period = period_start is None or entry.completed_at.date() >= period_start
        if in_current_period:
            period_total += entry.value
        result.append({
            "id": entry.id,
            "value": float(entry.value),
            "total": float(total),
            "period_total": float(period_total),
            "note": entry.note,
            "completed_at": entry.completed_at.isoformat(),
            "in_current_period": in_current_period,
        })
    return {"promise_id": promise.id, "tracking_mode": promise.tracking_mode, "target_value": float(promise.target_value or 1), "unit": promise.unit, "period_start": period_start.isoformat() if period_start else None, "entries": result}


@app.patch("/promises/{promise_id}", response_model=PromiseResponse)
def update_promise(promise_id: str, payload: PromiseUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    promise = get_promise_or_404(promise_id, db)
    ensure_space_access(promise.space_id, user, db)
    if promise.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the promise owner can edit it")
    changes = payload.model_dump(exclude_unset=True)
    if "unit" in changes and promise.tracking_mode != TrackingMode.CHECK_OFF and not (changes["unit"] or "").strip():
        raise HTTPException(status_code=422, detail="A unit is required for this tracking mode")
    for field, value in changes.items():
        setattr(promise, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(promise)
    return promise_view(promise)


@app.post("/promises/{promise_id}/archive", response_model=PromiseResponse)
def archive_promise(promise_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    promise = get_promise_or_404(promise_id, db)
    if promise.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the promise owner can archive it")
    promise.status = PromiseStatus.ARCHIVED.value
    db.commit()
    return promise_view(promise)


@app.post("/promises/{promise_id}/restore", response_model=PromiseResponse)
def restore_promise(promise_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    promise = get_promise_or_404(promise_id, db)
    ensure_space_access(promise.space_id, user, db)
    if promise.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the promise owner can restore it")
    if promise.status != PromiseStatus.ARCHIVED.value:
        raise HTTPException(status_code=409, detail="Only archived promises can be restored")
    promise.status = PromiseStatus.ACTIVE.value
    db.commit()
    db.refresh(promise)
    return promise_view(promise)


@app.post("/promises/{promise_id}/duplicate", response_model=PromiseResponse, status_code=status.HTTP_201_CREATED)
def duplicate_promise(promise_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = get_promise_or_404(promise_id, db)
    if source.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the promise owner can duplicate it")
    copy = Promise(id=str(uuid4()), space_id=source.space_id, owner_id=user.id, title=f"{source.title} (copy)",
        description=source.description, category=source.category, tracking_mode=source.tracking_mode, unit=source.unit,
        target_value=source.target_value, schedule_type=source.schedule_type, frequency=source.frequency,
        start_date=source.start_date, end_date=source.end_date, status=PromiseStatus.ACTIVE.value, why_it_matters=source.why_it_matters)
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return promise_view(copy)


@app.get("/groups")
def list_groups(db: Session = Depends(get_db), user: User = Depends(current_user)):
    memberships = db.query(Membership).filter_by(user_id=user.id).all()
    result = []
    for membership in memberships:
        group = db.get(Group, membership.group_id)
        space = db.get(Space, group.space_id)
        result.append({"id": group.id, "space_id": space.id, "name": space.name, "role": membership.role, "join_policy": group.join_policy, "timezone": group.timezone})
    return result


@app.post("/groups", status_code=status.HTTP_201_CREATED)
def create_group(payload: GroupCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    space = Space(id=str(uuid4()), name=payload.name.strip(), type=SpaceType.GROUP.value, owner_id=user.id)
    db.add(space)
    db.flush()
    group = Group(id=str(uuid4()), space_id=space.id, join_policy=payload.join_policy, timezone=payload.timezone)
    db.add(group)
    db.flush()
    membership = Membership(id=str(uuid4()), group_id=group.id, user_id=user.id, role="owner")
    db.add(membership)
    db.commit()
    return {"id": group.id, "space_id": space.id, "name": space.name, "role": "owner", "join_policy": group.join_policy, "timezone": group.timezone}


@app.patch("/groups/{group_id}")
def update_group(group_id: str, payload: GroupUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = group_membership_or_403(group_id, user.id, db)
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only an owner or admin can edit group settings")
    group = db.get(Group, group_id)
    space = db.get(Space, group.space_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        space.name = changes["name"].strip()
    if "join_policy" in changes:
        group.join_policy = changes["join_policy"]
    if "timezone" in changes:
        group.timezone = changes["timezone"].strip()
    db.commit()
    return {"id": group.id, "space_id": space.id, "name": space.name, "role": membership.role, "join_policy": group.join_policy, "timezone": group.timezone}


@app.get("/groups/{group_id}/members")
def group_members(group_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    group_membership_or_403(group_id, user.id, db)
    members = db.query(Membership).filter_by(group_id=group_id).all()
    return [{"user_id": member.user_id, "name": member.user.display_name, "email": member.user.email, "role": member.role} for member in members]


@app.patch("/groups/{group_id}/members/{member_user_id}")
def update_member_role(group_id: str, member_user_id: str, role: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = group_membership_or_403(group_id, user.id, db)
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail="Only the group owner can change roles")
    target = db.query(Membership).filter_by(group_id=group_id, user_id=member_user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Group member not found")
    if target.role == "owner" or role not in {"admin", "member"}:
        raise HTTPException(status_code=422, detail="The owner role cannot be changed")
    target.role = role
    db.commit()
    return {"user_id": target.user_id, "role": target.role}


@app.get("/groups/{group_id}/join-requests")
def list_join_requests(group_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = group_membership_or_403(group_id, user.id, db)
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only an owner or admin can review join requests")
    requests = db.query(JoinRequest).filter_by(group_id=group_id, status="pending").order_by(JoinRequest.created_at.asc()).all()
    return [{"id": request.id, "user_id": request.user_id, "name": request.user.display_name, "email": request.user.email, "created_at": request.created_at.isoformat()} for request in requests]


@app.post("/groups/{group_id}/join-requests/{request_id}/{decision}")
def decide_join_request(group_id: str, request_id: str, decision: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = group_membership_or_403(group_id, user.id, db)
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only an owner or admin can review join requests")
    if decision not in {"approve", "decline"}:
        raise HTTPException(status_code=422, detail="Decision must be approve or decline")
    request = db.query(JoinRequest).filter_by(id=request_id, group_id=group_id, status="pending").first()
    if request is None:
        raise HTTPException(status_code=404, detail="Pending join request not found")
    request.status = "approved" if decision == "approve" else "declined"
    if decision == "approve" and not db.query(Membership).filter_by(group_id=group_id, user_id=request.user_id).first():
        db.add(Membership(id=str(uuid4()), group_id=group_id, user_id=request.user_id, role="member"))
    db.commit()
    return {"id": request.id, "status": request.status}


@app.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = group_membership_or_403(group_id, user.id, db)
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail="Only the group owner can delete the group")
    group = db.get(Group, group_id)
    promise_ids = [promise.id for promise in db.query(Promise).filter_by(space_id=group.space_id).all()]
    if promise_ids:
        db.query(ProgressEntry).filter(ProgressEntry.promise_id.in_(promise_ids)).delete(synchronize_session=False)
    db.query(Promise).filter_by(space_id=group.space_id).delete(synchronize_session=False)
    db.query(JoinRequest).filter_by(group_id=group_id).delete(synchronize_session=False)
    db.query(Invite).filter_by(group_id=group_id).delete(synchronize_session=False)
    db.query(Membership).filter_by(group_id=group_id).delete(synchronize_session=False)
    db.delete(group)
    db.query(Space).filter_by(id=group.space_id).delete(synchronize_session=False)
    db.commit()


@app.post("/groups/{group_id}/invites", status_code=status.HTTP_201_CREATED)
def create_invite(group_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = group_membership_or_403(group_id, user.id, db)
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only an owner or admin can create invites")
    invite = Invite(id=str(uuid4()), group_id=group_id, token=token_urlsafe(24), created_by=user.id)
    db.add(invite)
    db.commit()
    # GitHub Pages serves this project below /promise-tracker/ and cannot resolve
    # server-side paths such as /join/{token}. A query-string invite keeps the
    # link inside the static single-page app instead of returning a Pages 404.
    return {"token": invite.token, "join_path": f"/promise-tracker/?invite={invite.token}", "join_policy": db.get(Group, group_id).join_policy}


@app.post("/invites/{token}/join")
def join_with_invite(token: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    invite = db.query(Invite).filter_by(token=token, is_active=True).first()
    if invite is None:
        raise HTTPException(status_code=404, detail="This invite link is invalid or has been revoked")
    group = db.get(Group, invite.group_id)
    if group.join_policy == "admin_approval":
        existing = db.query(JoinRequest).filter_by(group_id=group.id, user_id=user.id, status="pending").first()
        if existing is None:
            db.add(JoinRequest(id=str(uuid4()), group_id=group.id, user_id=user.id, status="pending"))
            db.commit()
        return {"status": "pending", "message": "Your request was sent to the group admins."}
    membership = db.query(Membership).filter_by(group_id=group.id, user_id=user.id).first()
    if membership is None:
        membership = Membership(id=str(uuid4()), group_id=group.id, user_id=user.id, role="member")
        db.add(membership)
        db.commit()
    space = db.get(Space, group.space_id)
    return {"id": group.id, "space_id": space.id, "name": space.name, "role": membership.role}


@app.get("/groups/{group_id}/dashboard")
def group_dashboard(group_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = db.query(Membership).filter_by(group_id=group_id, user_id=user.id).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="You are not a group member")
    group = db.get(Group, group_id)
    members = db.query(Membership).filter_by(group_id=group_id).all()
    promises = db.query(Promise).filter_by(space_id=group.space_id).all()
    return {
        "group_id": group_id,
        "members": [{"name": item.user.display_name, "role": item.role} for item in members],
        "promises": [promise_view(item) for item in promises],
        "upcoming_check_ins": [],
    }
