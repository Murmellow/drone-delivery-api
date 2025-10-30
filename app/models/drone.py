from __future__ import annotations

from sqlalchemy import Integer, String, Float, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from app.core.database import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # pragma: no cover
    from .location import Location
    from .order import Order

class DroneStatus(enum.Enum):
    AVAILABLE = "available"
    CHARGING = "charging"
    RESTOCKING = "restocking"
    LOADED = "loaded"
    IN_DELIVERY = "in_delivery"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"

class Drone(Base):
    __tablename__ = "drones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    serial_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    battery_level: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    status: Mapped[str] = mapped_column(String, nullable=False, default=DroneStatus.AVAILABLE.value)
    payload_capacity: Mapped[float] = mapped_column(Float, nullable=False)  # Max weight in kg
    range_km: Mapped[float] = mapped_column(Float, nullable=False)  # Max range in kilometers
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    current_location_id: Mapped[int] = mapped_column(Integer, ForeignKey("locations.id"), nullable=False)

    # Cargo tracking: stores list of {item_id, quantity, weight_kg}
    current_cargo: Mapped[list[dict[str, float | int]] | list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    current_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Relationships
    current_location: Mapped["Location"] = relationship("Location")
    deliveries: Mapped[list["Delivery"]] = relationship("Delivery", back_populates="drone")

class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    drone_id: Mapped[int] = mapped_column(Integer, ForeignKey("drones.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    start_location_id: Mapped[int] = mapped_column(Integer, ForeignKey("locations.id"), nullable=False)
    destination_location_id: Mapped[int] = mapped_column(Integer, ForeignKey("locations.id"), nullable=False)
    estimated_delivery_time: Mapped[int | None] = mapped_column(Integer, nullable=True)  # in minutes
    actual_delivery_time: Mapped[int | None] = mapped_column(Integer, nullable=True)  # in minutes

    # Relationships
    start_location: Mapped["Location"] = relationship("Location", foreign_keys=[start_location_id])
    destination_location: Mapped["Location"] = relationship("Location", foreign_keys=[destination_location_id])

    order: Mapped["Order"] = relationship("Order", back_populates="delivery")
    drone: Mapped["Drone"] = relationship("Drone", back_populates="deliveries")