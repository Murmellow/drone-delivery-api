from sqlalchemy import Column, Integer, String, Float
from app.core.database import Base

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    price: Column[float] = Column(Float, nullable=False, default=0.0)
    stock = Column(Integer, nullable=False, default=0)