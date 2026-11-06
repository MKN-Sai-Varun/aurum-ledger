from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_session
from app.deps import require_roles, staff_user
from app.domain.gold_math import format_pct, parse_wastage_pct
from app.models import (
    ROLE_FINANCE_HEAD,
    ItemCategory,
    Job,
    Karigar,
    KarigarWastage,
    User,
)

router = APIRouter(prefix="/api", tags=["karigars"])

NOT_FOUND = "Karigar not found."
RATE_HELP = "Enter a percentage from 0 to 100 with up to 2 decimals."


def _clean(value):
    return " ".join(value.split()) if isinstance(value, str) else value


class CategoryOut(BaseModel):
    id: int
    name: str


class WastageOut(BaseModel):
    category_id: int
    category: str
    wastage_pct: str


class KarigarOut(BaseModel):
    id: int
    name: str
    is_active: bool
    open_jobs: int
    wastage: list[WastageOut]


class KarigarCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)

    _tidy = field_validator("name", mode="before")(_clean)


class KarigarPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None

    _tidy = field_validator("name", mode="before")(_clean)

    @model_validator(mode="after")
    def at_least_one(self):
        if self.name is None and self.is_active is None:
            raise ValueError("Provide a name or an active flag.")
        return self


class RateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wastage_pct: str = Field(min_length=1, max_length=10)


def _build(db: Session, karigars: list[Karigar]) -> list[KarigarOut]:
    ids = [k.id for k in karigars]
    if not ids:
        return []
    rate_rows = db.execute(
        select(
            KarigarWastage.karigar_id,
            ItemCategory.id,
            ItemCategory.name,
            KarigarWastage.wastage_hundredths,
        )
        .join(ItemCategory, ItemCategory.id == KarigarWastage.category_id)
        .where(KarigarWastage.karigar_id.in_(ids))
        .order_by(ItemCategory.name)
    ).all()
    open_rows = db.execute(
        select(Job.karigar_id, func.count())
        .where(Job.status == "OPEN", Job.karigar_id.in_(ids))
        .group_by(Job.karigar_id)
    ).all()
    open_jobs = {karigar_id: count for karigar_id, count in open_rows}

    rates: dict[int, list[WastageOut]] = {}
    for karigar_id, category_id, category, hundredths in rate_rows:
        rates.setdefault(karigar_id, []).append(
            WastageOut(
                category_id=category_id,
                category=category,
                wastage_pct=format_pct(hundredths),
            )
        )
    return [
        KarigarOut(
            id=k.id,
            name=k.name,
            is_active=k.is_active,
            open_jobs=open_jobs.get(k.id, 0),
            wastage=rates.get(k.id, []),
        )
        for k in karigars
    ]


def _get_karigar(db: Session, karigar_id: int) -> Karigar:
    karigar = db.get(Karigar, karigar_id)
    if karigar is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return karigar


def _name_taken(db: Session, name: str, exclude_id: int | None = None) -> bool:
    query = select(Karigar.id).where(func.lower(Karigar.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Karigar.id != exclude_id)
    return db.scalar(query) is not None


def _open_job_count(db: Session, karigar_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.karigar_id == karigar_id, Job.status == "OPEN")
    )


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(
    db: Session = Depends(get_session), _user: User = Depends(staff_user)
):
    return [
        CategoryOut(id=c.id, name=c.name)
        for c in db.scalars(select(ItemCategory).order_by(ItemCategory.name))
    ]


@router.get("/karigars", response_model=list[KarigarOut])
def list_karigars(
    db: Session = Depends(get_session), _user: User = Depends(staff_user)
):
    karigars = db.scalars(select(Karigar).order_by(Karigar.name)).all()
    return _build(db, list(karigars))


@router.get("/karigars/{karigar_id}", response_model=KarigarOut)
def get_karigar(
    karigar_id: int,
    db: Session = Depends(get_session),
    _user: User = Depends(staff_user),
):
    return _build(db, [_get_karigar(db, karigar_id)])[0]


@router.post("/karigars", response_model=KarigarOut, status_code=201)
def create_karigar(
    body: KarigarCreate,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    if _name_taken(db, body.name):
        raise HTTPException(status_code=409, detail="A karigar with that name already exists.")
    karigar = Karigar(name=body.name)
    db.add(karigar)
    db.flush()
    record(db, user.id, "karigar.created", "karigar", karigar.id, body.name)
    db.commit()
    return _build(db, [karigar])[0]


@router.patch("/karigars/{karigar_id}", response_model=KarigarOut)
def update_karigar(
    karigar_id: int,
    body: KarigarPatch,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    karigar = _get_karigar(db, karigar_id)

    if body.name is not None and body.name.lower() != karigar.name.lower():
        if _name_taken(db, body.name, exclude_id=karigar.id):
            raise HTTPException(status_code=409, detail="A karigar with that name already exists.")
    if body.is_active is False and karigar.is_active:
        if _open_job_count(db, karigar.id) > 0:
            raise HTTPException(
                status_code=409,
                detail="This karigar has open jobs. Close them first.",
            )

    changes = []
    if body.name is not None and body.name != karigar.name:
        changes.append(f"name {karigar.name} -> {body.name}")
        karigar.name = body.name
    if body.is_active is not None and body.is_active != karigar.is_active:
        changes.append(f"active {karigar.is_active} -> {body.is_active}")
        karigar.is_active = body.is_active

    if changes:
        record(db, user.id, "karigar.updated", "karigar", karigar.id, "; ".join(changes))
        db.commit()
    return _build(db, [karigar])[0]


@router.put("/karigars/{karigar_id}/wastage/{category_id}", response_model=KarigarOut)
def set_rate(
    karigar_id: int,
    category_id: int,
    body: RateIn,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    karigar = _get_karigar(db, karigar_id)
    category = db.get(ItemCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Item category not found.")
    try:
        value = parse_wastage_pct(body.wastage_pct)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=RATE_HELP)

    row = db.scalar(
        select(KarigarWastage).where(
            KarigarWastage.karigar_id == karigar.id,
            KarigarWastage.category_id == category.id,
        )
    )
    before = format_pct(row.wastage_hundredths) if row else "none"
    if row is None:
        db.add(
            KarigarWastage(
                karigar_id=karigar.id,
                category_id=category.id,
                wastage_hundredths=value,
            )
        )
    else:
        row.wastage_hundredths = value
    record(
        db,
        user.id,
        "karigar.rate_set",
        "karigar",
        karigar.id,
        f"{karigar.name} / {category.name}: {before} -> {format_pct(value)}",
    )
    db.commit()
    return _build(db, [karigar])[0]