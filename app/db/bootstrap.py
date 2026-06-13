"""Repeatable demo database setup and reset."""

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.db.models.question import Question
from app.db.session import engine
from app.modules.embeddings.vector_index import rebuild_index, vector_index

SEED_PATH = Path(__file__).resolve().parents[2] / "seed_data" / "questions.json"


def seed_questions(db: Session) -> int:
    records = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    created = 0
    for record in records:
        if db.get(Question, record["id"]):
            continue
        db.add(Question(**record, created_by="system", reviewed_by="system"))
        created += 1
    db.commit()
    return created


def initialize_demo(db: Session, settings: Settings) -> dict:
    Base.metadata.create_all(bind=engine)
    seeded = seed_questions(db)
    indexed = rebuild_index(db, settings)
    return {"seededCount": seeded, **indexed}


def reset_demo(db: Session, settings: Settings) -> dict:
    vector_index.clear()
    db.close()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    from app.db.session import SessionLocal

    with SessionLocal() as fresh_db:
        seeded = seed_questions(fresh_db)
        indexed = rebuild_index(fresh_db, settings)
    return {"seededCount": seeded, **indexed}
