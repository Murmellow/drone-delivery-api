from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db, Base, engine
from app.models import customer as customer_models
from app.models import item as item_models
from app.models import order as order_models
from app.models import drone as drone_models
from app.models import location as location_models
from app.routers.drones import calculate_distance, estimate_delivery_time

from datetime import datetime, timezone
from typing import Any


router = APIRouter(prefix="/demo", tags=["demo"]) 


class DemoFlowRequest(BaseModel):
    flow: str = Field(description="Flow to run", examples=["single", "multi_queue", "existing_customer"])
    reset: bool = Field(default=False, description="Drop and recreate DB tables before running flow (idempotent demos)")


class DemoFlowResult(BaseModel):
    flow: str
    steps: list[dict[str, Any]]
    summary: dict[str, Any]


def _step(steps: list[dict[str, Any]], name: str, **data: Any) -> None:
    steps.append({"step": name, **data})


def _get_or_create_location(db: Session, name: str, lat: float, lon: float, altitude: float = 0.0) -> location_models.Location:
    loc = db.query(location_models.Location).filter(location_models.Location.name == name).first()
    if loc:
        return loc
    loc = location_models.Location(latitude=lat, longitude=lon, altitude=altitude, name=name)
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


def _get_or_create_customer(db: Session, first: str, last: str, email: str, phone: str, address: str, location_id: int) -> customer_models.Customer:
    cust = db.query(customer_models.Customer).filter(customer_models.Customer.email == email).first()
    if cust:
        return cust
    cust = customer_models.Customer(first_name=first, last_name=last, email=email, phone=phone, address=address, location_id=location_id)
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return cust


def _get_or_create_item(db: Session, title: str, price: float, stock: int, description: str = "") -> item_models.Item:
    itm = db.query(item_models.Item).filter(item_models.Item.title == title).first()
    if itm:
        # Ensure stock is sufficient for demo
        if getattr(itm, "stock", 0) < stock:
            setattr(itm, "stock", stock)
            db.commit()
            db.refresh(itm)
        return itm
    itm = item_models.Item(title=title, description=description, price=price, stock=stock)
    db.add(itm)
    db.commit()
    db.refresh(itm)
    return itm


def _get_or_create_drone(db: Session, model: str, serial: str, payload: float, range_km: float, current_location_id: int) -> drone_models.Drone:
    dr = db.query(drone_models.Drone).filter(drone_models.Drone.serial_number == serial).first()
    if dr:
        return dr
    dr = drone_models.Drone(model=model, serial_number=serial, payload_capacity=payload, range_km=range_km, current_location_id=current_location_id)
    db.add(dr)
    db.commit()
    db.refresh(dr)
    return dr


def _create_order(db: Session, customer: customer_models.Customer, items: list[tuple[item_models.Item, int]]) -> order_models.Order:
    # Compute total and check stock
    total: float = 0.0
    for itm, qty in items:
        db.refresh(itm)  # Ensure itm is loaded from DB and has actual values
        if int(getattr(itm, "stock", 0)) < qty:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for item {itm.title}")
        total += float(getattr(itm, "price", 0.0)) * qty

    # Decrement stock
    for itm, qty in items:
        setattr(itm, "stock", int(getattr(itm, "stock", 0)) - qty)

    # Create order
    ord_obj = order_models.Order(
        customer_id=customer.id,
        total_amount=total,
        status=order_models.OrderStatus.PENDING.value,
        delivery_address=customer.address or "",
        delivery_location_id=customer.location_id,
    )
    db.add(ord_obj)
    db.flush()  # get order id

    # Create order items with captured unit price
    for itm, qty in items:
        oi = order_models.OrderItem(order_id=ord_obj.id, item_id=itm.id, quantity=qty, unit_price=float(getattr(itm, "price")))
        db.add(oi)

    db.commit()
    db.refresh(ord_obj)
    return ord_obj


def _create_delivery(
    db: Session,
    order: order_models.Order,
    drone: drone_models.Drone,
    start_location_id: int,
    destination_location_id: int,
) -> tuple[drone_models.Delivery, float, int]:
    # Validate drone availability
    dr = db.query(drone_models.Drone).filter(
        drone_models.Drone.id == drone.id,
        drone_models.Drone.status == drone_models.DroneStatus.AVAILABLE.value,
        drone_models.Drone.is_active == True,
        drone_models.Drone.battery_level >= 20.0
    ).first()
    if not dr:
        raise HTTPException(status_code=400, detail="Drone is not available")

    # Compute distance and ETA
    start = db.query(location_models.Location).filter(location_models.Location.id == start_location_id).first()
    dest = db.query(location_models.Location).filter(location_models.Location.id == destination_location_id).first()
    assert start is not None and dest is not None
    distance_km: float = calculate_distance(
        float(getattr(start, "latitude")), 
        float(getattr(start, "longitude")), 
        float(getattr(dest, "latitude")), 
        float(getattr(dest, "longitude"))
    )
    eta_minutes: int = estimate_delivery_time(distance_km)

    delv = drone_models.Delivery(
        order_id=order.id,
        drone_id=drone.id,
        start_location_id=start_location_id,
        destination_location_id=destination_location_id,
        status="pending",
        estimated_delivery_time=eta_minutes,
    )
    setattr(dr, "status", str(drone_models.DroneStatus.IN_DELIVERY.value))
    db.add(delv)
    db.commit()
    db.refresh(delv)
    return delv, float(distance_km), int(eta_minutes)
    
    
def _complete_delivery(db: Session, delivery: drone_models.Delivery) -> None:
    # Mark delivery as completed
    setattr(delivery, "status", "completed")
    # Auto-unload cargo
    drone = delivery.drone
    setattr(drone, "current_cargo", [])
    setattr(drone, "current_weight", 0.0)
    # Move the drone to destination and mark available
    drone.status = drone_models.DroneStatus.AVAILABLE.value
    drone.current_location_id = delivery.destination_location_id
    db.commit()


def _load_cargo(db: Session, drone: drone_models.Drone, item: item_models.Item, quantity: int, weight_kg: float) -> None:
    """Load cargo onto a drone with capacity validation."""
    # Check drone status
    if drone.status not in [drone_models.DroneStatus.AVAILABLE.value, drone_models.DroneStatus.RESTOCKING.value]:
        raise HTTPException(status_code=400, detail=f"Drone must be available or restocking to load cargo. Current status: {drone.status}")
    
    # Check capacity
    current_weight = float(getattr(drone, "current_weight", 0.0))
    new_total_weight = current_weight + weight_kg
    if new_total_weight > float(getattr(drone, "payload_capacity")):
        raise HTTPException(status_code=400, detail=f"Payload capacity exceeded. Current: {current_weight}kg, Adding: {weight_kg}kg, Capacity: {getattr(drone, 'payload_capacity')}kg")
    
    # Add cargo
    cargo_list = list(getattr(drone, "current_cargo", []))
    cargo_list.append({"item_id": item.id, "quantity": quantity, "weight_kg": weight_kg})
    setattr(drone, "current_cargo", cargo_list)
    setattr(drone, "current_weight", new_total_weight)
    setattr(drone, "status", drone_models.DroneStatus.LOADED.value)
    db.commit()
    db.refresh(drone)


def _create_delivery_with_cargo_check(
    db: Session,
    order: order_models.Order,
    drone: drone_models.Drone,
    start_location_id: int,
    destination_location_id: int,
) -> tuple[drone_models.Delivery, float, int]:
    """Create delivery with cargo validation."""
    # Check drone has cargo loaded
    drone_status = str(getattr(drone, "status"))
    if drone_status != drone_models.DroneStatus.LOADED.value:
        raise HTTPException(status_code=400, detail="Drone has no cargo loaded. Load items onto the drone first")
    
    # Compute distance and ETA
    start = db.query(location_models.Location).filter(location_models.Location.id == start_location_id).first()
    dest = db.query(location_models.Location).filter(location_models.Location.id == destination_location_id).first()
    assert start is not None and dest is not None
    distance_km: float = calculate_distance(
        float(getattr(start, "latitude")), 
        float(getattr(start, "longitude")), 
        float(getattr(dest, "latitude")), 
        float(getattr(dest, "longitude"))
    )
    eta_minutes: int = estimate_delivery_time(distance_km)

    delv = drone_models.Delivery(
        order_id=order.id,
        drone_id=drone.id,
        start_location_id=start_location_id,
        destination_location_id=destination_location_id,
        status="pending",
        estimated_delivery_time=eta_minutes,
    )
    setattr(drone, "status", str(drone_models.DroneStatus.IN_DELIVERY.value))
    db.add(delv)
    db.commit()
    db.refresh(delv)
    return delv, float(distance_km), int(eta_minutes)


@router.post("/flow", response_model=DemoFlowResult)
def run_demo_flow(req: DemoFlowRequest, db: Session = Depends(get_db)) -> DemoFlowResult:
    steps: list[dict[str, Any]] = []

    if req.reset:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        _step(steps, "reset_db", status="ok")

    # Create shared data
    warehouse = _get_or_create_location(db, "Warehouse A", 40.0, -74.0)
    cust_home = _get_or_create_location(db, "Customer Home", 40.01, -74.01)
    office = _get_or_create_location(db, "Office", 40.02, -74.02)
    _step(steps, "locations", warehouse_id=warehouse.id, customer_home_id=cust_home.id, office_id=office.id)

    # make unique suffix for emails/serials in non-reset flows
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") if not req.reset else ""
    john_email = f"john{('-' + suffix) if suffix else ''}@example.com"
    jane_email = f"jane{('-' + suffix) if suffix else ''}@example.com"
    serial = f"DRN-001{('-' + suffix) if suffix else ''}"

    john = _get_or_create_customer(db, "John", "Doe", john_email, "123", "123 Main", getattr(cust_home, "id"))
    jane = _get_or_create_customer(db, "Jane", "Smith", jane_email, "456", "456 Oak", getattr(office, "id"))
    _step(steps, "customers", john_id=john.id, jane_id=jane.id)

    widget = _get_or_create_item(db, "Widget", 19.99, 100)
    gadget = _get_or_create_item(db, "Gadget", 49.99, 100)
    _step(steps, "items", widget_id=widget.id, gadget_id=gadget.id)

    drone = _get_or_create_drone(db, "DJI-X500", serial, 5.0, 30.0, getattr(warehouse, "id"))
    _step(steps, "drone", drone_id=drone.id, status=drone.status)

    if req.flow == "single":
        # Single delivery flow
        order = _create_order(db, john, [(widget, 2)])
        _step(steps, "order_created", order_id=order.id, status=order.status, total=order.total_amount)
        delivery, distance_km, eta = _create_delivery(db, order, drone, start_location_id=getattr(warehouse, "id"), destination_location_id=getattr(cust_home, "id"))
        _step(steps, "delivery_created", delivery_id=delivery.id, drone_status=delivery.drone.status, distance_km=distance_km, eta_minutes=eta)
        return DemoFlowResult(flow=req.flow, steps=steps, summary={
            "order_id": order.id,
            "delivery_id": delivery.id,
            "drone_status": delivery.drone.status,
            "distance_km": distance_km,
            "estimated_delivery_minutes": eta,
        })

    if req.flow == "multi_queue":
        # First order and delivery
        order1 = _create_order(db, john, [(gadget, 1)])
        _step(steps, "order1_created", order_id=order1.id, status=order1.status)
        delivery1, distance1_km, eta1 = _create_delivery(db, order1, drone, start_location_id=getattr(warehouse, "id"), destination_location_id=getattr(cust_home, "id"))
        _step(steps, "delivery1_created", delivery_id=delivery1.id, drone_status=delivery1.drone.status, distance_km=distance1_km, eta_minutes=eta1)

        # Second order while drone is busy
        order2 = _create_order(db, jane, [(gadget, 2)])
        _step(steps, "order2_created", order_id=order2.id, status=order2.status)

        # Attempt assigning delivery 2 while drone busy -> expect 400
        try:
            _create_delivery(db, order2, drone, start_location_id=getattr(warehouse, "id"), destination_location_id=getattr(office, "id"))
            # If it didn't fail, mark unexpected
            _step(steps, "delivery2_attempt", result="unexpected_success")
        except HTTPException as ex:
            _step(steps, "delivery2_attempt", result="failed", status_code=ex.status_code, detail=ex.detail)

        # Complete first delivery, freeing the drone
        _complete_delivery(db, delivery1)
        _step(steps, "delivery1_completed", drone_status=delivery1.drone.status)

        # Assign delivery 2 now
        delivery2, distance2_km, eta2 = _create_delivery(db, order2, drone, start_location_id=getattr(warehouse, "id"), destination_location_id=getattr(office, "id"))
        _step(steps, "delivery2_created", delivery_id=delivery2.id, drone_status=delivery2.drone.status, distance_km=distance2_km, eta_minutes=eta2)

        return DemoFlowResult(flow=req.flow, steps=steps, summary={
            "order1_id": order1.id,
            "delivery1_id": delivery1.id,
            "order2_id": order2.id,
            "delivery2_id": delivery2.id,
            "drone_status": delivery2.drone.status,
            "delivery1_distance_km": distance1_km,
            "delivery1_estimated_minutes": eta1,
            "delivery2_distance_km": distance2_km,
            "delivery2_estimated_minutes": eta2,
        })

    if req.flow == "existing_customer":
        # Workflow: Existing customer places order -> cargo loading -> delivery -> completion
        # This simulates a complete order-to-delivery cycle with cargo management
        
        # Create order for John (existing customer)
        order = _create_order(db, john, [(widget, 1), (gadget, 1)])
        _step(steps, "order_created", order_id=order.id, customer=john.first_name, total=order.total_amount, status=order.status)
        
        # Load cargo onto drone at warehouse
        # Calculate total weight (assuming 0.5kg per widget, 1.0kg per gadget)
        widget_weight = 0.5
        gadget_weight = 1.0
        
        try:
            _load_cargo(db, drone, widget, 1, widget_weight)
            _step(steps, "cargo_loaded", item="Widget", quantity=1, weight_kg=widget_weight, drone_status=drone.status)
            
            _load_cargo(db, drone, gadget, 1, gadget_weight)
            _step(steps, "cargo_loaded", item="Gadget", quantity=1, weight_kg=gadget_weight, drone_status=drone.status, total_weight=widget_weight + gadget_weight)
        except HTTPException as ex:
            _step(steps, "cargo_load_failed", status_code=ex.status_code, detail=ex.detail)
            raise
        
        # Create delivery with cargo validation
        try:
            delivery, distance_km, eta = _create_delivery_with_cargo_check(
                db, order, drone, 
                start_location_id=getattr(warehouse, "id"), 
                destination_location_id=getattr(cust_home, "id")
            )
            _step(steps, "delivery_created", delivery_id=delivery.id, drone_status=delivery.drone.status, distance_km=distance_km, eta_minutes=eta)
        except HTTPException as ex:
            _step(steps, "delivery_creation_failed", status_code=ex.status_code, detail=ex.detail)
            raise
        
        # Simulate delivery in progress
        _step(steps, "delivery_in_transit", delivery_id=delivery.id, status="Drone en route to customer")
        
        # Complete delivery
        _complete_delivery(db, delivery)
        db.refresh(delivery)
        db.refresh(drone)
        _step(steps, "delivery_completed", 
              delivery_id=delivery.id, 
              delivery_status=delivery.status,
              drone_status=drone.status, 
              drone_location="Customer Home",
              cargo_unloaded=True)
        
        return DemoFlowResult(flow=req.flow, steps=steps, summary={
            "order_id": order.id,
            "delivery_id": delivery.id,
            "customer": f"{john.first_name} {john.last_name}",
            "items_delivered": 2,
            "total_amount": order.total_amount,
            "distance_km": distance_km,
            "estimated_delivery_minutes": eta,
            "final_drone_status": drone.status,
            "final_drone_location": "Customer Home",
            "cargo_weight_delivered_kg": widget_weight + gadget_weight,
        })

    raise HTTPException(status_code=400, detail="Unknown flow. Use 'single', 'multi_queue', or 'existing_customer'.")
