"""Start-up preparation for hosts whose disk is thrown away on restart.

When AUTO_SEED=true the tables are created and, if the database is empty, the
demo data is loaded. Nothing happens otherwise, so local development and the
tests are unaffected.
"""
import os

from sqlalchemy import select

from app.db import Base, SessionLocal as _SessionLocal, engine as _engine
from app.models import User
from app.seed import seed_database


def bootstrap(engine=_engine, session_factory=_SessionLocal) -> None:
    if os.getenv("AUTO_SEED", "").strip().lower() != "true":
        return
    clerk = os.getenv("DEMO_CLERK_PASSWORD", "").strip()
    finance = os.getenv("DEMO_FINANCE_PASSWORD", "").strip()
    if not clerk or not finance:
        raise RuntimeError(
            "AUTO_SEED needs DEMO_CLERK_PASSWORD and DEMO_FINANCE_PASSWORD."
        )
    Base.metadata.create_all(engine)
    with session_factory() as session:
        if session.scalar(select(User.id).limit(1)) is None:
            seed_database(session, clerk, finance)