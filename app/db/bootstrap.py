"""Repeatable demo database setup and reset."""

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy import inspect, text
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
    ensure_demo_schema()
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


def ensure_demo_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "paraphrase_candidates" in table_names:
            _add_missing_columns(
                connection,
                inspector,
                "paraphrase_candidates",
                {
                    "option_a": "TEXT",
                    "option_b": "TEXT",
                    "option_c": "TEXT",
                    "option_d": "TEXT",
                },
            )
        if "document_question_jobs" in table_names:
            _add_missing_columns(
                connection,
                inspector,
                "document_question_jobs",
                {
                    "prompt_version": "VARCHAR(64)",
                    "completed_chunk_count": "INTEGER NOT NULL DEFAULT 0",
                    "failed_chunk_count": "INTEGER NOT NULL DEFAULT 0",
                    "chunk_errors": "JSON NOT NULL DEFAULT '[]'",
                    "llm_call_count": "INTEGER NOT NULL DEFAULT 0",
                    "total_prompt_tokens": "INTEGER NOT NULL DEFAULT 0",
                    "total_completion_tokens": "INTEGER NOT NULL DEFAULT 0",
                    "total_tokens": "INTEGER NOT NULL DEFAULT 0",
                    "total_latency_ms": "INTEGER NOT NULL DEFAULT 0",
                    "estimated_cost_usd": "FLOAT NOT NULL DEFAULT 0",
                },
            )
        if "document_question_candidates" in table_names:
            _add_missing_columns(
                connection,
                inspector,
                "document_question_candidates",
                {
                    "generation_key": "VARCHAR(128)",
                    "quality_score": "FLOAT",
                    "llm_validation": "JSON",
                },
            )
        if "document_chunks" in table_names:
            _add_missing_columns(
                connection,
                inspector,
                "document_chunks",
                {
                    "section_id": "VARCHAR(64)",
                    "parent_chunk_id": "VARCHAR(64)",
                    "chunk_type": "VARCHAR(32) NOT NULL DEFAULT 'generation'",
                    "section_path": "VARCHAR(1000)",
                    "token_count": "INTEGER NOT NULL DEFAULT 0",
                    "quality_flags": "JSON NOT NULL DEFAULT '[]'",
                    "previous_chunk_id": "VARCHAR(64)",
                    "next_chunk_id": "VARCHAR(64)",
                },
            )


def _add_missing_columns(connection, inspector, table_name: str, additions: dict[str, str]) -> None:
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    for column_name, column_type in additions.items():
        if column_name not in existing:
            connection.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            )
