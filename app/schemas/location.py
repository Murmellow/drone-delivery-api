from pydantic import BaseModel, Field, field_validator

class LocationBase(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    altitude: float = Field(default=0.0, ge=-100, le=10000)  # Reasonable altitude range in meters
    name: str | None = None

    @field_validator('latitude')
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        return round(v, 6)  # Round to 6 decimal places (approx. 11cm precision)

    @field_validator('longitude')
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        return round(v, 6)

    @field_validator('altitude')
    @classmethod
    def validate_altitude(cls, v: float) -> float:
        return round(v, 1)  # Round to 1 decimal place for altitude

class LocationCreate(LocationBase):
    pass

class Location(LocationBase):
    id: int

    class Config:
        from_attributes = True