from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base

class DroneStatus(enum.Enum):
    AVAILABLE = "available"
    CHARGING = "charging"
    IN_DELIVERY = "in_delivery"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"

class Drone(Base):
    __tablename__ = "drones"

    id = Column(Integer, primary_key=True, index=True)
    model = Column(String, nullable=False)
    serial_number = Column(String, unique=True, nullable=False)
    battery_level: Column[float] = Column(Float, nullable=False, default=100.0)
    status = Column(String, nullable=False, default=DroneStatus.AVAILABLE.value)
    payload_capacity: Column[float]  = Column(Float, nullable=False)  # Maximum weight in kg
    range_km: Column[float] = Column(Float, nullable=False)  # Maximum range in kilometers
    is_active = Column(Boolean, default=True)
    current_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)

    # Relationships
    current_location = relationship("Location")  # Could be GPS coordinates or zone identifier
    
    # Relationships
    deliveries = relationship("Delivery", back_populates="drone")

class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    drone_id = Column(Integer, ForeignKey("drones.id"), nullable=False)
    status = Column(String, nullable=False, default="pending")
    start_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    destination_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    estimated_delivery_time = Column(Integer)  # in minutes
    actual_delivery_time = Column(Integer)  # in minutes

    # Relationships
    start_location = relationship("Location", foreign_keys=[start_location_id])
    destination_location = relationship("Location", foreign_keys=[destination_location_id])
    
    # Relationships
    order = relationship("Order", back_populates="delivery")
    drone = relationship("Drone", back_populates="deliveries")