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
