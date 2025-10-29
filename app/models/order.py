from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
from app.core.database import Base

class OrderStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class Order(Base):
    __tablename__ = "orders"

    id: Column[int] = Column(Integer, primary_key=True, index=True)
    customer_id: Column[int] = Column(Integer, ForeignKey("customers.id"), nullable=False)
    total_amount: Column[float] = Column(Float, nullable=False, default=0.0)
    status: Column[str] = Column(String, nullable=False, default=OrderStatus.PENDING.value)
    order_date: Column[datetime] = Column(DateTime, nullable=False, default=datetime.now(timezone.utc))
    queue_position: Column[int] = Column(Integer, index=True)  # Position in the delivery queue
    priority: Column[int] = Column(Integer, default=0)  # Higher number = higher priority
    delivery_address: Column[str] = Column(String)  # Physical address for reference
    delivery_location_id: Column[int] = Column(Integer, ForeignKey("locations.id"), nullable=False)
    
    # Relationships
    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")
    delivery = relationship("Delivery", back_populates="order", uselist=False)
    delivery_location = relationship("Location")

class OrderItem(Base):
    __tablename__ = "order_items"

    id: Column[int] = Column(Integer, primary_key=True, index=True)
    order_id: Column[int] = Column(Integer, ForeignKey("orders.id"), nullable=False)
    item_id: Column[int] = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity: Column[int] = Column(Integer, nullable=False)
    unit_price: Column[float] = Column(Float, nullable=False)
    
    # Relationships
    order = relationship("Order", back_populates="items")
    item = relationship("Item")