from pydantic import BaseModel, Field
from typing import Any

class DroneBase(BaseModel):
    model: str
    serial_number: str
    payload_capacity: float = Field(..., gt=0)
    range_km: float = Field(..., gt=0)
    current_location_id: int
    
class DroneCreate(DroneBase):
    pass

class Drone(DroneBase):
    id: int
    battery_level: float
    status: str
    is_active: bool
    current_cargo: list[dict[str, Any]] = []
    current_weight: float = 0.0

    class Config:
        from_attributes = True

class LoadCargoRequest(BaseModel):
    """Request to load items onto a drone at a warehouse"""
    item_id: int
    quantity: int = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)

class UnloadCargoRequest(BaseModel):
    """Request to unload items from a drone"""
    item_id: int
    quantity: int = Field(..., gt=0)

class MoveDroneRequest(BaseModel):
    """Request to move a drone to a different location (restricted to warehouses)."""
    location_id: int

class DeliveryBase(BaseModel):
    order_id: int
    drone_id: int
    start_location_id: int
    destination_location_id: int
    estimated_delivery_time: int | None = None
class DeliveryCreate(DeliveryBase):
    pass

class Delivery(DeliveryBase):
    id: int
    status: str
    actual_delivery_time: int | None = None
    class Config:
        from_attributes = True