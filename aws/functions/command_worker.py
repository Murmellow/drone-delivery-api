import json
import os
from typing import Any, Dict, List

from app.core.database import SessionLocal, Base, engine
from app.models import drone as drone_models
from app.models import item as item_models
from app.models import order as order_models
from app.models import location as location_models

# Ensure tables exist (for demo with SQLite /tmp)
Base.metadata.create_all(bind=engine)


def _load_cargo(db, drone_id: int, item_id: int, quantity: int, weight_kg: float) -> Dict[str, Any]:
    drone = db.query(drone_models.Drone).filter(drone_models.Drone.id == drone_id).first()
    item = db.query(item_models.Item).filter(item_models.Item.id == item_id).first()
    if not drone or not item:
        return {"ok": False, "detail": "Drone or Item not found"}

    status = str(getattr(drone, "status"))
    if status not in [drone_models.DroneStatus.AVAILABLE.value, drone_models.DroneStatus.RESTOCKING.value]:
        return {"ok": False, "detail": f"Drone not in loadable status: {status}"}

    current_weight = float(getattr(drone, "current_weight", 0.0))
    capacity = float(getattr(drone, "payload_capacity", 0.0))
    if current_weight + weight_kg > capacity:
        return {"ok": False, "detail": "Payload capacity exceeded"}

    cargo_list = list(getattr(drone, "current_cargo", []))
    cargo_list.append({"item_id": item_id, "quantity": quantity, "weight_kg": weight_kg})
    setattr(drone, "current_cargo", cargo_list)
    setattr(drone, "current_weight", current_weight + weight_kg)
    setattr(drone, "status", drone_models.DroneStatus.LOADED.value)
    db.commit()
    db.refresh(drone)
    return {"ok": True, "drone_id": drone_id, "current_weight": getattr(drone, "current_weight", 0.0)}


def _create_delivery(db, order_id: int, drone_id: int, start_location_id: int, destination_location_id: int) -> Dict[str, Any]:
    order = db.query(order_models.Order).filter(order_models.Order.id == order_id).first()
    drone = db.query(drone_models.Drone).filter(drone_models.Drone.id == drone_id).first()
    if not order or not drone:
        return {"ok": False, "detail": "Order or Drone not found"}

    # Must be loaded
    if str(getattr(drone, "status")) != drone_models.DroneStatus.LOADED.value:
        return {"ok": False, "detail": "Drone has no cargo loaded"}

    delv = drone_models.Delivery(
        order_id=order.id,
        drone_id=drone.id,
        start_location_id=start_location_id,
        destination_location_id=destination_location_id,
        status="pending",
        estimated_delivery_time=15,
    )
    setattr(drone, "status", drone_models.DroneStatus.IN_DELIVERY.value)
    db.add(delv)
    db.commit()
    db.refresh(delv)
    return {"ok": True, "delivery_id": delv.id, "drone_status": drone.status}


def _complete_delivery(db, delivery_id: int, drone_id: int) -> Dict[str, Any]:
    delivery = db.query(drone_models.Delivery).filter(drone_models.Delivery.id == delivery_id).first()
    if not delivery:
        return {"ok": False, "detail": "Delivery not found"}
    setattr(delivery, "status", "completed")
    drone = db.query(drone_models.Drone).filter(drone_models.Drone.id == drone_id).first()
    if drone:
        setattr(drone, "current_cargo", [])
        setattr(drone, "current_weight", 0.0)
        setattr(drone, "status", drone_models.DroneStatus.AVAILABLE.value)
        setattr(drone, "current_location_id", delivery.destination_location_id)
    db.commit()
    return {"ok": True, "delivery_id": delivery_id}


def handler(event, context):  # SQS batch
    # event["Records"] contains SQS messages
    results: List[Dict[str, Any]] = []
    db = SessionLocal()
    try:
        for rec in event.get("Records", []):
            body = json.loads(rec.get("body", "{}"))
            msg_type = body.get("type")
            if msg_type == "LoadCargoRequested":
                res = _load_cargo(
                    db,
                    int(body.get("drone_id")),
                    int(body.get("item_id")),
                    int(body.get("quantity", 1)),
                    float(body.get("weight_kg", 0.0)),
                )
            elif msg_type == "DeliveryRequested":
                res = _create_delivery(
                    db,
                    int(body.get("order_id")),
                    int(body.get("drone_id")),
                    int(body.get("start_location_id")),
                    int(body.get("destination_location_id")),
                )
            elif msg_type == "DeliveryCompletionRequested":
                res = _complete_delivery(
                    db,
                    int(body.get("delivery_id")),
                    int(body.get("drone_id")),
                )
            else:
                res = {"ok": False, "detail": f"Unknown message type: {msg_type}"}
            results.append(res)
        return {"results": results}
    finally:
        db.close()
