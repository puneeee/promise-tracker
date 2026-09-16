from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import os
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


DATABASE_PATH = Path(__file__).resolve().parents[1] / "promise_tracker.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

# Render exposes Postgres URLs with the postgres:// scheme. SQLAlchemy uses the
# explicit psycopg driver scheme that is installed by requirements.txt.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)

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


def group_membership_or_403(group_id: str, user_id: str, db: Session) -> Membership:
    membership = db.query(Membership).filter_by(group_id=group_id, user_id=user_id).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="You are not a group member")
    return membership


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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(db: Session = Depends(get_db)) -> User:
    # Temporary local identity. Google token verification replaces this in the auth milestone.
    user = db.get(User, "demo-user")
    if user is None:
        user = User(id="demo-user", email="you@example.com", display_name="You")
        db.add(user)
        db.add(Space(id="personal-demo", name="My promises", type=SpaceType.PERSONAL.value, owner_id=user.id))
        db.commit()
    return user


def promise_view(promise: Promise) -> PromiseResponse:
    progress = sum((entry.value for entry in promise.progress_entries), Decimal("0"))
    if promise.tracking_mode == TrackingMode.CHECK_OFF.value:
        progress = Decimal("1") if progress else Decimal("0")
    target = promise.target_value or Decimal("1")
    percent = min(100, int((progress / target) * 100)) if target else 0
    return PromiseResponse(
        id=promise.id, title=promise.title, category=promise.category,
        tracking_mode=promise.tracking_mode, unit=promise.unit, target_value=promise.target_value,
        schedule_type=promise.schedule_type, frequency=promise.frequency, status=promise.status,
        is_locked=promise.is_locked, current_progress=progress, completion_percent=percent,
        owner_name=promise.owner.display_name,
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
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "display_name": user.display_name}


@app.get("/spaces/{space_id}/promises", response_model=list[PromiseResponse])
def list_promises(space_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_space_access(space_id, user, db)
    promises = db.query(Promise).filter_by(space_id=space_id).order_by(Promise.created_at.desc()).all()
    return [promise_view(promise) for promise in promises]


@app.post("/spaces/{space_id}/promises", response_model=PromiseResponse, status_code=status.HTTP_201_CREATED)
def create_promise(payload: PromiseCreate, space_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_space_access(space_id, user, db)
    if payload.schedule_type == "date_range" and (not payload.start_date or not payload.end_date or payload.end_date < payload.start_date):
        raise HTTPException(status_code=422, detail="A date-range promise needs a valid start and end date")
    if payload.tracking_mode != TrackingMode.CHECK_OFF and payload.target_value is None:
        raise HTTPException(status_code=422, detail="A target value is required for this tracking mode")
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
    db.add(ProgressEntry(id=str(uuid4()), promise_id=promise.id, owner_id=user.id, value=payload.value, note=payload.note))
    db.flush()
    current = sum((entry.value for entry in promise.progress_entries), Decimal("0"))
    if promise.schedule_type == "date_range" and promise.target_value and current >= promise.target_value:
        promise.status = PromiseStatus.COMPLETED.value
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
        result.append({"id": group.id, "space_id": space.id, "name": space.name, "role": membership.role, "join_policy": group.join_policy})
    return result


@app.post("/groups", status_code=status.HTTP_201_CREATED)
def create_group(payload: GroupCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    space = Space(id=str(uuid4()), name=payload.name.strip(), type=SpaceType.GROUP.value, owner_id=user.id)
    group = Group(id=str(uuid4()), space_id=space.id, join_policy=payload.join_policy, timezone=payload.timezone)
    membership = Membership(id=str(uuid4()), group_id=group.id, user_id=user.id, role="owner")
    db.add_all([space, group, membership])
    db.commit()
    return {"id": group.id, "space_id": space.id, "name": space.name, "role": "owner", "join_policy": group.join_policy}


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
        raise HTTPException(status_code=409, detail="This group requires admin approval before joining")
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
