"""Rebuild all approved question embeddings."""

from app.core.config import get_settings
from app.db.session import SessionLocal, create_tables
from app.modules.embeddings.vector_index import rebuild_index


def main() -> None:
    create_tables()
    with SessionLocal() as db:
        print(rebuild_index(db, get_settings()))


if __name__ == "__main__":
    main()
