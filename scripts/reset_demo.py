"""Reset, reseed, and reindex the demo database."""

from app.core.config import get_settings
from app.db.bootstrap import reset_demo
from app.db.session import SessionLocal


def main() -> None:
    db = SessionLocal()
    print(reset_demo(db, get_settings()))


if __name__ == "__main__":
    main()
