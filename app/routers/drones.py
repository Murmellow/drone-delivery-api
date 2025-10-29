from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.query import Query
from app.core.database import get_db
from app.models import drone as drone_models
from app.models import order as order_models
from app.schemas import drone as schemas
import math
from typing import Any
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

@router.post("/{drone_id}/load", response_model=schemas.Drone)
def load_cargo(
    drone_id: int,
    cargo: schemas.LoadCargoRequest,
    db: Session = Depends(get_db)
) -> drone_models.Drone:
    """Load items onto a drone at a warehouse. Drone must be at a warehouse location and in AVAILABLE or RESTOCKING status."""
    drone: drone_models.Drone | None = db.query(drone_models.Drone).filter(drone_models.Drone.id == drone_id).first()
    if drone is None:
        raise HTTPException(status_code=404, detail="Drone not found")
    
    # Check drone status
    if drone.status not in [drone_models.DroneStatus.AVAILABLE.value, drone_models.DroneStatus.RESTOCKING.value]:
        raise HTTPException(status_code=400, detail=f"Drone must be available or restocking to load cargo (current status: {drone.status})")
    
    # Check payload capacity - cast to Any for runtime values
    current_weight: float = getattr(drone, "current_weight", 0.0)
    new_weight = current_weight + cargo.weight_kg
    payload_capacity: float = getattr(drone, "payload_capacity", 0.0)
    if new_weight > payload_capacity:
        raise HTTPException(status_code=400, detail=f"Exceeds payload capacity ({new_weight} kg > {payload_capacity} kg)")
    
    # Add to cargo manifest
    cargo_data: Any = getattr(drone, "current_cargo", None)
    current_cargo: list[dict[str, Any]] = list(cargo_data) if cargo_data else []
    
    # Check if item already exists in cargo
    found = False
    for item in current_cargo:
        if item.get("item_id") == cargo.item_id:
            item["quantity"] = item.get("quantity", 0) + cargo.quantity
            item["weight_kg"] = item.get("weight_kg", 0.0) + cargo.weight_kg
            found = True
            break
    
    if not found:
        current_cargo.append({
            "item_id": cargo.item_id,
            "quantity": cargo.quantity,
            "weight_kg": cargo.weight_kg
        })
    
    setattr(drone, "current_cargo", current_cargo)
    setattr(drone, "current_weight", new_weight)
    setattr(drone, "status", drone_models.DroneStatus.LOADED.value)
    
    db.commit()
    db.refresh(drone)
    return drone

@router.post("/{drone_id}/unload", response_model=schemas.Drone)
def unload_cargo(
    drone_id: int,
    cargo: schemas.UnloadCargoRequest,
    db: Session = Depends(get_db)
) -> drone_models.Drone:
    """Unload items from a drone. This happens after delivery."""
    drone: drone_models.Drone | None = db.query(drone_models.Drone).filter(drone_models.Drone.id == drone_id).first()
    if drone is None:
        raise HTTPException(status_code=404, detail="Drone not found")
    
    cargo_data: Any = getattr(drone, "current_cargo", None)
    current_cargo: list[dict[str, Any]] = list(cargo_data) if cargo_data else []
    
    # Find and remove item from cargo
    found = False
    item_to_remove: dict[str, Any] | None = None
    for item in current_cargo:
        if item.get("item_id") == cargo.item_id:
            current_qty: int = item.get("quantity", 0)
            if current_qty < cargo.quantity:
                raise HTTPException(status_code=400, detail=f"Not enough quantity to unload (have {current_qty}, requested {cargo.quantity})")
            
            item["quantity"] = current_qty - cargo.quantity
            total_qty = current_qty
            weight_per_unit: float = item.get("weight_kg", 0.0) / total_qty if total_qty > 0 else 0.0
            item["weight_kg"] = item.get("weight_kg", 0.0) - (weight_per_unit * cargo.quantity)
            
            current_weight: float = getattr(drone, "current_weight", 0.0)
            setattr(drone, "current_weight", current_weight - (weight_per_unit * cargo.quantity))
            
            # Remove item entirely if quantity is 0
            if item["quantity"] == 0:
                item_to_remove = item
            
            found = True
            break
    
    if not found:
        raise HTTPException(status_code=404, detail="Item not found in cargo")
    
    if item_to_remove:
        current_cargo.remove(item_to_remove)
    
    setattr(drone, "current_cargo", current_cargo)
    
    # If cargo is empty, set status to available
    if len(current_cargo) == 0:
        setattr(drone, "status", drone_models.DroneStatus.AVAILABLE.value)
        setattr(drone, "current_weight", 0.0)
    
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
    
    # Check if drone is available OR loaded (has cargo ready)
    drone = db.query(drone_models.Drone).filter(
        drone_models.Drone.id == delivery.drone_id,
        drone_models.Drone.is_active == True,
        drone_models.Drone.battery_level >= 20.0
    ).first()
    
    if not drone:
        raise HTTPException(status_code=404, detail="Drone not found")
    
    # Allow delivery creation if drone is available or loaded
    valid_statuses = [drone_models.DroneStatus.AVAILABLE.value, drone_models.DroneStatus.LOADED.value]
    if drone.status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Drone is not available")
    
    # Check if drone has the required items loaded (basic check - could be enhanced with item_id validation)
    cargo_data: Any = getattr(drone, "current_cargo", None)
    current_cargo: list[dict[str, Any]] = list(cargo_data) if cargo_data else []
    
    if not current_cargo:
        raise HTTPException(
            status_code=400, 
            detail="Drone has no cargo loaded. Load items onto the drone first using POST /drones/{drone_id}/load"
        )
    
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
    
    # Update drone status and location
    drone = delivery.drone
    
    # Automatically unload all cargo upon delivery completion
    setattr(drone, "current_cargo", [])
    setattr(drone, "current_weight", 0.0)
    setattr(drone, "status", drone_models.DroneStatus.AVAILABLE.value)
    
    # Move drone to the delivery destination (by id to avoid relationship issues)
    setattr(drone, "current_location_id", delivery.destination_location_id)
    
    db.commit()
    return {"message": "Delivery completed successfully", "cargo_unloaded": True}