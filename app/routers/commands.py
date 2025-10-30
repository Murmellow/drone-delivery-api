from __future__ import annotations

import json
import uuid
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.outbox import Outbox
from typing import Any

# Optional local bus import for local workflow endpoint
try:
    from app.services.local_bus import local_bus
except Exception:  # pragma: no cover
    local_bus = None  # type: ignore

router = APIRouter(prefix="/commands", tags=["commands"])


class CreateDeliveryCommand(BaseModel):
    order_id: int
    drone_id: int
    start_location_id: int
    destination_location_id: int


@router.post("/deliveries", status_code=status.HTTP_202_ACCEPTED)
def request_create_delivery(cmd: CreateDeliveryCommand, db: Session = Depends(get_db)) -> dict[str, Any]:
    """CQRS command endpoint: enqueue DeliveryRequested to the outbox.

    When USE_CQRS is enabled and the outbox publisher is configured with SQS,
    this will be forwarded to the AWS queue asynchronously by the background publisher.
    """
    request_id = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "type": "DeliveryRequested",
        "request_id": request_id,
        "order_id": cmd.order_id,
        "drone_id": cmd.drone_id,
        "start_location_id": cmd.start_location_id,
        "destination_location_id": cmd.destination_location_id,
    }
    ob = Outbox(
        event_type="DeliveryRequested",
        aggregate_type="delivery",
        aggregate_id=str(cmd.drone_id),
        payload=json.dumps(payload),
        status="pending",
    )
    db.add(ob)
    db.commit()
    db.refresh(ob)

    return {
        "accepted": True,
        "request_id": request_id,
        "outbox_id": ob.id,
        "message": "Delivery request accepted. Track results via logs or read models.",
        "cqrs": settings.USE_CQRS,
    }


class LocalWorkflowBody(BaseModel):
    order_id: int
    drone_id: int
    item_id: int
    quantity: int
    weight_kg: float
    start_location_id: int
    destination_location_id: int
    delivery_id: int


@router.post("/workflow/start-local", status_code=status.HTTP_202_ACCEPTED)
def start_local_workflow(body: LocalWorkflowBody) -> dict[str, Any]:
    """Start a local in-process workflow without AWS credentials.
    Sends SQS-equivalent commands through the LocalQueueBus in order.
    """
    if not local_bus:
        return {"accepted": False, "detail": "Local bus not available"}

    # Enqueue steps in order, grouped by drone_id
    group_id = str(body.drone_id)
    local_bus.send({
        "type": "LoadCargoRequested",
        "drone_id": body.drone_id,
        "item_id": body.item_id,
        "quantity": body.quantity,
        "weight_kg": body.weight_kg,
    }, group_id, f"load-{body.drone_id}-{body.item_id}")

    local_bus.send({
        "type": "DeliveryRequested",
        "order_id": body.order_id,
        "drone_id": body.drone_id,
        "start_location_id": body.start_location_id,
        "destination_location_id": body.destination_location_id,
    }, group_id, f"delivery-{body.order_id}")

    local_bus.send({
        "type": "DeliveryCompletionRequested",
        "delivery_id": body.delivery_id,
        "drone_id": body.drone_id,
    }, group_id, f"complete-{body.delivery_id}")

    return {"accepted": True, "detail": "Local workflow started"}
