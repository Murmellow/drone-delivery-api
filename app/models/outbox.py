from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.core.database import Base

class Outbox(Base):
    __tablename__ = "outbox"
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(100), nullable=False)
    aggregate_type = Column(String(100), nullable=False)
    aggregate_id = Column(String(100), nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending|published|failed
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
