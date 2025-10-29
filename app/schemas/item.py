from pydantic import BaseModel, Field

class ItemBase(BaseModel):
    title: str
    description: str | None = None
    price: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)

class ItemCreate(ItemBase):
    pass

class Item(ItemBase):
    id: int

    class Config:
        from_attributes = True