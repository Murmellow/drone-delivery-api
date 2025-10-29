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
    flow: str = Field(description="Flow to run", examples=["single", "multi_queue"])
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
        if itm.stock < stock:
            itm.stock = stock
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
        if itm.stock < qty:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for item {itm.title}")
        total += float(itm.price) * qty

    # Decrement stock
    for itm, qty in items:
        itm.stock -= qty

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
        oi = order_models.OrderItem(order_id=ord_obj.id, item_id=itm.id, quantity=qty, unit_price=float(itm.price))
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
    distance_km: float = calculate_distance(start.latitude, start.longitude, dest.latitude, dest.longitude)
    eta_minutes: int = estimate_delivery_time(distance_km)

    delv = drone_models.Delivery(
        order_id=order.id,
        drone_id=drone.id,
        start_location_id=start_location_id,
        destination_location_id=destination_location_id,
        status="pending",
        estimated_delivery_time=eta_minutes,
    )
    drone.status = drone_models.DroneStatus.IN_DELIVERY.value
    db.add(delv)
    db.commit()
    db.refresh(delv)
    return delv, float(distance_km), int(eta_minutes)


def _complete_delivery(db: Session, delivery: drone_models.Delivery) -> None:
    delivery.status = "completed"
    # Move the drone to destination and mark available
    drone = delivery.drone
    drone.status = drone_models.DroneStatus.AVAILABLE.value
    drone.current_location_id = delivery.destination_location_id
    db.commit()


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

    john = _get_or_create_customer(db, "John", "Doe", john_email, "123", "123 Main", cust_home.id)
    jane = _get_or_create_customer(db, "Jane", "Smith", jane_email, "456", "456 Oak", office.id)
    _step(steps, "customers", john_id=john.id, jane_id=jane.id)

    widget = _get_or_create_item(db, "Widget", 19.99, 100)
    gadget = _get_or_create_item(db, "Gadget", 49.99, 100)
    _step(steps, "items", widget_id=widget.id, gadget_id=gadget.id)

    drone = _get_or_create_drone(db, "DJI-X500", serial, 5.0, 30.0, warehouse.id)
    _step(steps, "drone", drone_id=drone.id, status=drone.status)

    if req.flow == "single":
        # Single delivery flow
        order = _create_order(db, john, [(widget, 2)])
        _step(steps, "order_created", order_id=order.id, status=order.status, total=order.total_amount)
        delivery, distance_km, eta = _create_delivery(db, order, drone, start_location_id=warehouse.id, destination_location_id=cust_home.id)
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
        delivery1, distance1_km, eta1 = _create_delivery(db, order1, drone, start_location_id=warehouse.id, destination_location_id=cust_home.id)
        _step(steps, "delivery1_created", delivery_id=delivery1.id, drone_status=delivery1.drone.status, distance_km=distance1_km, eta_minutes=eta1)

        # Second order while drone is busy
        order2 = _create_order(db, jane, [(gadget, 2)])
        _step(steps, "order2_created", order_id=order2.id, status=order2.status)

        # Attempt assigning delivery 2 while drone busy -> expect 400
        try:
            _create_delivery(db, order2, drone, start_location_id=warehouse.id, destination_location_id=office.id)
            # If it didn't fail, mark unexpected
            _step(steps, "delivery2_attempt", result="unexpected_success")
        except HTTPException as ex:
            _step(steps, "delivery2_attempt", result="failed", status_code=ex.status_code, detail=ex.detail)

        # Complete first delivery, freeing the drone
        _complete_delivery(db, delivery1)
        _step(steps, "delivery1_completed", drone_status=delivery1.drone.status)

        # Assign delivery 2 now
        delivery2, distance2_km, eta2 = _create_delivery(db, order2, drone, start_location_id=warehouse.id, destination_location_id=office.id)
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

    raise HTTPException(status_code=400, detail="Unknown flow. Use 'single' or 'multi_queue'.")
