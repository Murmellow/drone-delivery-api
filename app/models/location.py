from __future__ import annotations

from sqlalchemy import Integer, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    altitude: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    name: Mapped[str | None] = mapped_column(String, index=True, nullable=True)  # Optional name

    @property
    def longitude_degrees(self) -> float:
        """Get longitude as a float value in degrees"""
        return float(getattr(self, 'longitude', 0.0))

    @property
    def latitude_degrees(self) -> float:
        """Get latitude as a float value in degrees"""
        return float(getattr(self, 'latitude', 0.0))

    @property
    def altitude_meters(self) -> float:
        """Get altitude as a float value in meters"""
        return float(getattr(self, 'altitude', 0.0))

    def distance_to(self, other_location: 'Location') -> float:
        """Calculate distance to another location in kilometers"""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth's radius in kilometers

        lat1, lon1 = map(radians, [self.latitude_degrees, self.longitude_degrees])
        lat2, lon2 = map(radians, [other_location.latitude_degrees, other_location.longitude_degrees])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c