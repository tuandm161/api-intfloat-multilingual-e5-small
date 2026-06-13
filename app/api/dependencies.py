"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db

SettingsDependency = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[Session, Depends(get_db)]
