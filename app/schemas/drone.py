from pydantic import BaseModel, Field

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

    class Config:
        from_attributes = True

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