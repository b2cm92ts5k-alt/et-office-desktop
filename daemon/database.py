"""SQLite + SQLAlchemy — tasks, logs, proposals (M1-3)
agent registry ใช้ JSON file (agent_registry.py) ตาม blueprint
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Column, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = os.environ.get("ET_OFFICE_DB", str(DATA_DIR / "etoffice.sqlite"))

engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class TaskRow(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(32), unique=True, index=True)
    message = Column(Text, default="")
    agent_id = Column(String(32), index=True, default="")
    agent_name = Column(String(64), default="")
    status = Column(String(16), index=True, default="routing")
    output = Column(Text, default="")
    created_at = Column(String(40), default="")
    finished_at = Column(String(40), default="")


class LogRow(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(String(40), index=True, default="")
    agent_id = Column(String(32), index=True, default="")
    type = Column(String(24), index=True, default="info")
    message = Column(Text, default="")


class ProposalRow(Base):
    __tablename__ = "proposals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    proposal_id = Column(String(32), unique=True, index=True)
    title = Column(Text, default="")
    detail = Column(Text, default="")
    proposed_by = Column(Text, default="")   # comma-separated agent ids
    status = Column(String(16), index=True, default="pending")
    note = Column(Text, default="")
    created_at = Column(String(40), default="")


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
