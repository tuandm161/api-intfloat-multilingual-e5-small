"""Load seed questions into the configured database."""

from app.db.bootstrap import seed_questions as load_seed_questions
from app.db.session import SessionLocal, create_tables


def seed_questions() -> int:
    create_tables()
    with SessionLocal() as db:
        return load_seed_questions(db)


if __name__ == "__main__":
    print(f"Seeded {seed_questions()} questions.")
