from __future__ import annotations

from sqlalchemy import String, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # pragma: no cover
    from .location import Location
    from .order import Order
from app.core.database import Base

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)  # Physical address for reference
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("locations.id"), nullable=False)

    # Relationships
    location: Mapped["Location"] = relationship("Location")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="customer")