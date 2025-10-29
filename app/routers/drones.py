from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.query import Query
from app.core.database import get_db
from app.models import drone as drone_models
from app.models import order as order_models
from app.schemas import drone as schemas
from datetime import datetime, timezone
import math
router = APIRouter(prefix="/drones", tags=["drones"])

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the Haversine distance between two points in kilometers."""
    R = 6371  # Earth radius in kilometers
    phi1: float = math.radians(lat1)
    phi2: float = math.radians(lat2)
    delta_phi: float = math.radians(lat2 - lat1)
    delta_lambda: float = math.radians(lon2 - lon1)
    a: float = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c: float = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def estimate_delivery_time(distance_km: float, speed_kmh: float = 40.0) -> int:
    """
    Estimate delivery time in minutes given distance in kilometers and drone speed (default 40 km/h).
    Returns the estimated time rounded up to the nearest minute.
    """
    if speed_kmh <= 0:
        raise ValueError("Speed must be greater than zero")
    time_hours = distance_km / speed_kmh
    time_minutes = math.ceil(time_hours * 60)
    return time_minutes

async def process_delivery_queue(db: Session):
    """Process pending orders in the delivery queue"""
    # Get available drones
    available_drones = db.query(drone_models.Drone).filter(
        drone_models.Drone.status == drone_models.DroneStatus.AVAILABLE.value,
        drone_models.Drone.is_active == True,
        drone_models.Drone.battery_level >= 20.0
    ).all()

    if not available_drones:
        return

    # Get pending orders ordered by priority (high to low) and then queue position
    pending_orders: list[order_models.Order] = db.query(order_models.Order).filter(
        order_models.Order.status == order_models.OrderStatus.PENDING.value
    ).order_by(
        order_models.Order.priority.desc(),
        order_models.Order.queue_position
    ).all()

    for order in pending_orders:
        # Find the nearest available drone
        nearest_drone: drone_models.Drone | None = None
        min_distance = float('inf')
        
        for drone in available_drones:
            distance: float = calculate_distance(
                drone.current_location.latitude,
                drone.current_location.longitude,
                order.delivery_location.latitude,
                order.delivery_location.longitude
            )
            
            if float(distance) <= float(getattr(drone, "range_km", 0)) / 2 and distance < min_distance:  # Ensure drone can make round trip
                nearest_drone = drone
                min_distance: float = distance

        if nearest_drone:
            # Create delivery
            delivery = drone_models.Delivery(
                order_id=order.id,
                drone_id=nearest_drone.id,
                start_location_id=nearest_drone.current_location_id,
                destination_location_id=order.delivery_location_id,
                estimated_delivery_time=estimate_delivery_time(min_distance)
            )
            
            # Update statuses
            setattr(nearest_drone, "status", drone_models.DroneStatus.IN_DELIVERY.value)
            setattr(order, "status", order_models.OrderStatus.PROCESSING.value)
            
            db.add(delivery)
            available_drones.remove(nearest_drone)
            
            if not available_drones:  # No more drones available
                break

    db.commit()

@router.post("/", response_model=schemas.Drone)
def create_drone(drone: schemas.DroneCreate, db: Session = Depends(get_db)) -> schemas.Drone:
    db_drone: drone_models.Drone | None = db.query(drone_models.Drone).filter(drone_models.Drone.serial_number == drone.serial_number).first()
    if db_drone:
        raise HTTPException(status_code=400, detail="Drone with this serial number already exists")
    
    db_drone = drone_models.Drone(**drone.model_dump())
    db.add(db_drone)
    db.commit()
    db.refresh(db_drone)
    return db_drone

@router.get("/", response_model=list[schemas.Drone])
def read_drones(
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
    db: Session = Depends(get_db)
) -> list[schemas.Drone]:
    query: Query[drone_models.Drone] = db.query(drone_models.Drone)
    if status:
        query = query.filter(drone_models.Drone.status == status)
    drones: list[drone_models.Drone] = query.offset(skip).limit(limit).all()
    return [schemas.Drone.model_validate(drone) for drone in drones]

@router.get("/available", response_model=list[schemas.Drone])
def read_available_drones(db: Session = Depends(get_db)) -> list[schemas.Drone]:
    drones = db.query(drone_models.Drone).filter(
        drone_models.Drone.status == drone_models.DroneStatus.AVAILABLE.value,
        drone_models.Drone.is_active == True,
        drone_models.Drone.battery_level >= 20.0
    ).all()
    return [schemas.Drone.model_validate(drone) for drone in drones]

@router.get("/{drone_id}", response_model=schemas.Drone)
def read_drone(drone_id: int, db: Session = Depends(get_db)) -> schemas.Drone:
    drone = db.query(drone_models.Drone).filter(drone_models.Drone.id == drone_id).first()
    if drone is None:
        raise HTTPException(status_code=404, detail="Drone not found")
    return drone

@router.patch("/{drone_id}/status", response_model=schemas.Drone)
def update_drone_status(
    drone_id: int,
    status: str,
    db: Session = Depends(get_db)
) -> drone_models.Drone:
    drone: drone_models.Drone | None = db.query(drone_models.Drone).filter(drone_models.Drone.id == drone_id).first()
    if drone is None:
        raise HTTPException(status_code=404, detail="Drone not found")
    
    if status not in [s.value for s in drone_models.DroneStatus]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    setattr(drone, "status", drone_models.DroneStatus(status).value)
    db.commit()
    db.refresh(drone)
    return drone

@router.post("/deliveries/", response_model=schemas.Delivery)
def create_delivery(delivery: schemas.DeliveryCreate, db: Session = Depends(get_db)):
    # Check if order exists and doesn't have a delivery yet
    order = db.query(order_models.Order).filter(order_models.Order.id == delivery.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if hasattr(order, 'delivery') and order.delivery:
        raise HTTPException(status_code=400, detail="Order already has a delivery assigned")
    
    # Check if drone is available
    drone = db.query(drone_models.Drone).filter(
        drone_models.Drone.id == delivery.drone_id,
        drone_models.Drone.status == drone_models.DroneStatus.AVAILABLE.value,
        drone_models.Drone.is_active == True,
        drone_models.Drone.battery_level >= 20.0
    ).first()
    
    if not drone:
        raise HTTPException(status_code=400, detail="Drone is not available")
    
    # Create delivery and update drone status
    db_delivery = drone_models.Delivery(**delivery.model_dump())
    setattr(drone, "status", drone_models.DroneStatus.IN_DELIVERY.value)
    
    db.add(db_delivery)
    db.commit()
    db.refresh(db_delivery)
    return db_delivery

@router.get("/deliveries/{delivery_id}", response_model=schemas.Delivery)
def read_delivery(delivery_id: int, db: Session = Depends(get_db)):
    delivery = db.query(drone_models.Delivery).filter(drone_models.Delivery.id == delivery_id).first()
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return delivery

@router.patch("/deliveries/{delivery_id}/complete")
def complete_delivery(delivery_id: int, db: Session = Depends(get_db)):
    delivery = db.query(drone_models.Delivery).filter(drone_models.Delivery.id == delivery_id).first()
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    
    setattr(delivery, "status", "completed")
    # Optionally compute actual_delivery_time if timestamps are tracked; omitted here as created_at is not present
    # setattr(delivery, "actual_delivery_time", int((datetime.now(timezone.utc) - delivery.created_at).total_seconds() / 60))
    
    # Update drone status
    drone = delivery.drone
    setattr(drone, "status", drone_models.DroneStatus.AVAILABLE.value)
    # Move drone to the delivery destination (by id to avoid relationship issues)
    setattr(drone, "current_location_id", delivery.destination_location_id)
    
    db.commit()
    return {"message": "Delivery completed successfully"}