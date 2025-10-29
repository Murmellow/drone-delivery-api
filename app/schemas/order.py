from pydantic import BaseModel, Field
from datetime import datetime

class OrderItemBase(BaseModel):
    item_id: int
    quantity: int = Field(gt=0)

class OrderItemCreate(OrderItemBase):
    pass

class OrderItem(OrderItemBase):
    id: int
    order_id: int
    unit_price: float

    class Config:
        from_attributes = True

class OrderBase(BaseModel):
    customer_id: int
    delivery_address: str


class OrderCreate(OrderBase):
    items: list[OrderItemCreate]

class Order(OrderBase):
    id: int
    total_amount: float
    status: str
    order_date: datetime
    items: list[OrderItem]
    class Config:
        from_attributes = True