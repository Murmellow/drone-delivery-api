from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id: Column[int] = Column(Integer, primary_key=True, index=True)
    email: Column[str] = Column(String, unique=True, index=True)
    username: Column[str] = Column(String, unique=True, index=True)
    hashed_password: Column[str] = Column(String)

    # Relationships
    orders = relationship("Order", back_populates="user")
