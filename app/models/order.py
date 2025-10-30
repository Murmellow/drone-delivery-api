from __future__ import annotations

from sqlalchemy import Integer, String, ForeignKey, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
import enum
from app.core.database import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # pragma: no cover
    from .customer import Customer
    from .location import Location
    from .drone import Delivery
    from .item import Item

class OrderStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String, nullable=False, default=OrderStatus.PENDING.value)
    order_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now(timezone.utc))
    queue_position: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)  # Position in queue
    priority: Mapped[int] = mapped_column(Integer, default=0)
    delivery_address: Mapped[str | None] = mapped_column(String, nullable=True)
    delivery_location_id: Mapped[int] = mapped_column(Integer, ForeignKey("locations.id"), nullable=False)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order")
    delivery: Mapped["Delivery | None"] = relationship("Delivery", back_populates="order", uselist=False)
    delivery_location: Mapped["Location"] = relationship("Location")

class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="items")
    item: Mapped["Item"] = relationship("Item")