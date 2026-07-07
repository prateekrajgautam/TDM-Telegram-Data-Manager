"""SQLAlchemy models and session management for TDM."""
import datetime
import json
from contextlib import contextmanager

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import settings

Base = declarative_base()


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    phone = Column(String, unique=True, nullable=False)
    session_name = Column(String, nullable=False)  # file under sessions_dir
    first_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class StorageTarget(Base):
    __tablename__ = "storage_targets"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    type = Column(String, nullable=False)  # "local" | "sftp"
    config_json = Column(Text, nullable=False, default="{}")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    def config(self) -> dict:
        return json.loads(self.config_json or "{}")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    job_type = Column(String, nullable=False)  # "download" | "export"
    dialog_id = Column(String, nullable=False)
    dialog_name = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending/running/completed/failed/cancelled
    progress = Column(Integer, default=0)
    total = Column(Integer, default=0)
    storage_target_id = Column(Integer, ForeignKey("storage_targets.id"), nullable=True)
    output_path = Column(String, nullable=True)
    options_json = Column(Text, nullable=False, default="{}")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    storage_target = relationship("StorageTarget")
    media_items = relationship("MediaItem", back_populates="job", cascade="all, delete-orphan")

    def options(self) -> dict:
        return json.loads(self.options_json or "{}")


class MediaItem(Base):
    __tablename__ = "media_items"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    message_id = Column(Integer, nullable=False)
    filename = Column(String, nullable=True)
    path = Column(String, nullable=True)
    size = Column(Integer, nullable=True)
    checksum = Column(String, nullable=True)
    media_type = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending/downloaded/verified/failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    job = relationship("Job", back_populates="media_items")


_engine = None
_SessionLocal = None


def init_db():
    global _engine, _SessionLocal
    settings.ensure_dirs()
    _engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(_engine)


@contextmanager
def get_session():
    if _SessionLocal is None:
        init_db()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
