import time
import os
from behave import given, when, then # type: ignore
from behave.runner import Context # type: ignore
import anyio
from typing import Any, Protocol, TypeVar, cast
from collections.abc import Callable
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.outbox import Outbox
from app.models.drone import Drone, Delivery
from app.core.config import settings

# Typed aliases for behave step decorators to satisfy type checkers
F = TypeVar("F", bound=Callable[..., Any])

def typed_given(pattern: str) -> Callable[[F], F]:
    return given(pattern)  # type: ignore

def typed_when(pattern: str) -> Callable[[F], F]:
    return when(pattern)  # type: ignore

def typed_then(pattern: str) -> Callable[[F], F]:
    return then(pattern)  # type: ignore

class ResponseLike(Protocol):
    status_code: int
    text: str
    def json(self) -> Any: ...

class HttpClientLike(Protocol):
    async def post(self, path: str, *, json: dict[str, Any]) -> ResponseLike: ...
    async def get(self, path: str) -> ResponseLike: ...

class ContextWithClient(Protocol):
    client: HttpClientLike
    response: ResponseLike | None
    locations: dict[str, Any]
    customer: dict[str, Any]
    items: dict[str, Any]
    drone: dict[str, Any]
    order: dict[str, Any]
    delivery: dict[str, Any]
    cqrs_response: dict[str, Any]

# Helpers to run async client calls
async def _post(context: ContextWithClient, path: str, json: dict[str, Any]) -> ResponseLike:
    client = context.client
    resp = await client.post(path, json=json)
    context.response = resp
    return resp

async def _get(context: ContextWithClient, path: str) -> ResponseLike:
    client = context.client
    resp = await client.get(path)
    context.response = resp
    return resp

@typed_given('CQRS mode is enabled with local queue')
def step_enable_cqrs_local(context: Context):
    """Enable CQRS mode and ensure local queue is used (no AWS SQS URL)."""
    # Set environment variables to ensure CQRS mode with local queue
    os.environ["USE_CQRS"] = "true"
    if "AWS_SQS_QUEUE_URL" in os.environ:
        del os.environ["AWS_SQS_QUEUE_URL"]
    # Note: In a real test environment, you'd restart the app or ensure these
    # settings are picked up. For Behave with environment.py setup, this should work.

@typed_when('I start local workflow for drone "{serial}" with item "{item_title}" quantity {quantity:d} weight {weight:f}')
def step_start_local_workflow(context: Context, serial: str, item_title: str, quantity: int, weight: float):
    """Start a local CQRS workflow by calling the start-local endpoint."""
    context_with_client = cast(ContextWithClient, context)
    
    async def _run():
        order_id = context_with_client.order["id"]
        drone_id = context_with_client.drone["id"]
        item_id = context_with_client.items[item_title]
        start_location_id = context_with_client.drone["current_location_id"]
        destination_location_id = context_with_client.customer["location_id"]
        
        # Use a placeholder delivery_id (will be created by workflow)
        # The workflow creates the delivery, but for completion step we need an ID
        # We'll use 1 as a placeholder since the DB is fresh per scenario
        delivery_id = 1
        
        resp = await _post(context_with_client, "/api/v1/commands/workflow/start-local", {
            "order_id": order_id,
            "drone_id": drone_id,
            "item_id": item_id,
            "quantity": quantity,
            "weight_kg": weight,
            "start_location_id": start_location_id,
            "destination_location_id": destination_location_id,
            "delivery_id": delivery_id
        })
        assert resp.status_code in [200, 202], resp.text
        context_with_client.cqrs_response = resp.json()
    
    anyio.run(_run)

@typed_then('after waiting {seconds:d} seconds the outbox should have published messages')
def step_wait_for_outbox_publish(context: Context, seconds: int):
    """Wait for async processing and verify outbox messages are published."""
    time.sleep(seconds)
    
    # Query the database to check outbox status
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as session:
        stmt = select(Outbox).where(Outbox.status == "published")
        published_messages = session.execute(stmt).scalars().all()
        assert len(published_messages) > 0, "No messages were published to the outbox"

@typed_then('after waiting {seconds:d} seconds the local queue should have processed messages')
def step_wait_for_local_queue(context: Context, seconds: int):
    """Wait for async processing via local queue (bypasses outbox)."""
    # Local queue processes messages immediately in the background
    time.sleep(seconds)

@typed_then('the drone "{serial}" should have cargo loaded')
def step_verify_drone_has_cargo(context: Context, serial: str):
    """Verify that the drone has cargo loaded."""
    context_with_client = cast(ContextWithClient, context)
    
    # Query directly from database with fresh session to see worker's committed changes
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as session:
        drone_id = context_with_client.drone["id"]
        stmt = select(Drone).where(Drone.id == drone_id)
        drone = session.execute(stmt).scalar_one_or_none()
        assert drone is not None, f"Drone {serial} not found"
        print(f"DEBUG: Drone {serial} cargo: {drone.current_cargo}, weight: {drone.current_weight}")
        assert len(drone.current_cargo) > 0, f"Drone {serial} has no cargo loaded"
        assert drone.current_weight > 0, f"Drone {serial} weight is {drone.current_weight}"

@typed_then('a delivery should exist for the last order')
def step_verify_delivery_exists(context: Context):
    """Verify that a delivery exists for the last order."""
    context_with_client = cast(ContextWithClient, context)
    
    # Query the database to check for delivery
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as session:
        order_id = context_with_client.order["id"]
        stmt = select(Delivery).where(Delivery.order_id == order_id)
        delivery = session.execute(stmt).scalar_one_or_none()
        assert delivery is not None, f"No delivery found for order {order_id}"
        # Store delivery in context for further assertions
        context_with_client.delivery = {
            "id": str(delivery.id),
            "order_id": str(delivery.order_id),
            "drone_id": str(delivery.drone_id),
            "status": delivery.status,
            "start_location_id": str(delivery.start_location_id) if delivery.start_location_id else None,
            "destination_location_id": str(delivery.destination_location_id) if delivery.destination_location_id else None
        }

@typed_then('the delivery should be completed')
def step_verify_delivery_completed(context: Context):
    """Verify that the delivery status is completed."""
    context_with_client = cast(ContextWithClient, context)
    
    # Re-fetch delivery from database to get latest status
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as session:
        order_id = context_with_client.order["id"]
        stmt = select(Delivery).where(Delivery.order_id == order_id)
        delivery = session.execute(stmt).scalar_one_or_none()
        assert delivery is not None, f"No delivery found for order {order_id}"
        assert delivery.status == "completed", f"Delivery status is {delivery.status}, expected 'completed'"

@typed_then('the drone "{serial}" should have no cargo')
def step_verify_drone_no_cargo(context: Context, serial: str):
    """Verify that the drone has no cargo."""
    context_with_client = cast(ContextWithClient, context)
    
    # Query directly from database with fresh session to see worker's committed changes
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as session:
        drone_id = context_with_client.drone["id"]
        stmt = select(Drone).where(Drone.id == drone_id)
        drone = session.execute(stmt).scalar_one_or_none()
        assert drone is not None, f"Drone {serial} not found"
        assert len(drone.current_cargo) == 0, f"Drone {serial} still has cargo: {drone.current_cargo}"
        assert drone.current_weight == 0.0, f"Drone {serial} weight is {drone.current_weight}"

@typed_when('I load cargo onto drone "{serial}" with item "{item_title}" quantity {quantity:d} weight {weight:f}')
def step_load_cargo_on_drone(context: Context, serial: str, item_title: str, quantity: int, weight: float):
    """Manually load cargo onto a drone using the direct API (not CQRS)."""
    context_with_client = cast(ContextWithClient, context)
    
    async def _run():
        drone_id = context_with_client.drone["id"]
        item_id = context_with_client.items[item_title]
        
        # Load cargo via POST /api/v1/drones/{drone_id}/load
        resp = await _post(context_with_client, f"/api/v1/drones/{drone_id}/load", {
            "item_id": item_id,
            "quantity": quantity,
            "weight_kg": weight
        })
        assert resp.status_code == 200, resp.text
        context_with_client.drone = resp.json()
    
    anyio.run(_run)

@typed_when('I request delivery creation via CQRS command for the last order using drone "{serial}"')
def step_request_delivery_via_cqrs(context: Context, serial: str):
    """Request delivery creation via the CQRS command endpoint."""
    context_with_client = cast(ContextWithClient, context)
    
    async def _run():
        order_id = context_with_client.order["id"]
        drone_id = context_with_client.drone["id"]
        start_location_id = context_with_client.drone["current_location_id"]
        destination_location_id = context_with_client.customer["location_id"]
        
        resp = await _post(context_with_client, "/api/v1/commands/deliveries", {
            "order_id": order_id,
            "drone_id": drone_id,
            "start_location_id": start_location_id,
            "destination_location_id": destination_location_id
        })
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
        context_with_client.cqrs_response = resp.json()
    
    anyio.run(_run)

@typed_then('the CQRS command should be accepted')
def step_verify_cqrs_accepted(context: Context):
    """Verify that the CQRS command was accepted (202 status with request_id)."""
    context_with_client = cast(ContextWithClient, context)
    
    assert context_with_client.cqrs_response is not None, "No CQRS response found"
    assert "request_id" in context_with_client.cqrs_response, "Missing request_id in response"
    assert "outbox_id" in context_with_client.cqrs_response, "Missing outbox_id in response"

@typed_then('a delivery should exist for the last order with drone "{serial}"')
def step_verify_delivery_with_drone(context: Context, serial: str):
    """Verify that a delivery exists for the last order with the specified drone."""
    context_with_client = cast(ContextWithClient, context)
    
    # Query the database to check for delivery
    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as session:
        order_id = context_with_client.order["id"]
        drone_id = context_with_client.drone["id"]
        stmt = select(Delivery).where(
            Delivery.order_id == order_id,
            Delivery.drone_id == drone_id
        )
        delivery = session.execute(stmt).scalar_one_or_none()
        assert delivery is not None, f"No delivery found for order {order_id} with drone {serial}"
        # Store delivery in context
        context_with_client.delivery = {
            "id": str(delivery.id),
            "order_id": str(delivery.order_id),
            "drone_id": str(delivery.drone_id),
            "status": delivery.status
        }
