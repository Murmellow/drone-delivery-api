from behave import given, when, then # type: ignore
from behave.runner import Context # type: ignore
import anyio
from typing import Any, Protocol, TypeVar, cast, TypedDict
from collections.abc import Callable, Iterable, Mapping

# Typed aliases for behave step decorators to satisfy type checkers
F = TypeVar("F", bound=Callable[..., Any])
StepDecorator = Callable[[str], Callable[[F], F]]
# Optionally, you can define your own typed step decorators if you want type safety:
def typed_given(pattern: str) -> Callable[[F], F]:
    return given(pattern)  # type: ignore

def typed_when(pattern: str) -> Callable[[F], F]:
    return when(pattern)  # type: ignore

def typed_then(pattern: str) -> Callable[[F], F]:
    return then(pattern)  # type: ignore

# Use these in your step definitions if you want type checking:
# @typed_given('...')
# def step_impl(...): ...

class ResponseLike(Protocol):
    status_code: int
    text: str
    def json(self) -> Any: ...

class HttpClientLike(Protocol):
    async def post(self, path: str, *, json: dict[str, Any]) -> ResponseLike: ...
    async def get(self, path: str) -> ResponseLike: ...
    async def patch(self, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> ResponseLike: ...

class ContextWithClient(Protocol):
    client: HttpClientLike
    response: ResponseLike | None
    locations: dict[str, Any]
    customer: dict[str, Any]  # Added to satisfy type checker
    items: dict[str, Any]     # Added to satisfy type checker for items
    drone: dict[str, Any]     # Added to satisfy type checker for drone
    order: dict[str, Any]     # Added to satisfy type checker for order
    delivery: dict[str, Any]  # Added to satisfy type checker for delivery
    table: Iterable[Mapping[str, str]]  # Behave step table (rows with string values)

class OrderLine(TypedDict):
    item_id: str
    quantity: int

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

async def _patch(context: ContextWithClient, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> ResponseLike:
    client = context.client
    resp = await client.patch(path, params=params, json=json)
    context.response = resp
    return resp

@given('a location named "{name}" at latitude {lat:f} and longitude {lon:f}')  # type: ignore[misc]
def step_create_location(context: Context, name: str, lat: float, lon: float):
    # Explicitly cast context to ContextWithClient for type checking
    context_with_client = cast(ContextWithClient, context)

    # Ensure context has required attributes for ContextWithClient
    if not hasattr(context_with_client, "client"):
        raise AttributeError("Context is missing required 'client' attribute for HTTP calls.")
    if not hasattr(context_with_client, "response"):
        context_with_client.response = None  # type: ignore # type: ResponseLike | None

    # Ensure context has 'locations' attribute for storing location ids
    if not hasattr(context_with_client, "locations"):
        context_with_client.locations = {}

    async def _run():
        resp = await _post(context_with_client, "/api/v1/locations/", {
            "latitude": lat,
            "longitude": lon,
            "name": name
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        context_with_client.locations[name] = data["id"]
    anyio.run(_run)

@typed_given('a customer exists with first name "{first}", last name "{last}", email "{email}", phone "{phone}", address "{address}", and location "{loc_name}"')
def step_create_customer(context: Context, first: str, last: str, email: str, phone: str, address: str, loc_name: str):
    # Explicitly cast context to ContextWithClient for type checking
    context_with_client = cast(ContextWithClient, context)

    # Ensure context has required attributes for ContextWithClient
    if not hasattr(context_with_client, "client"):
        raise AttributeError("Context is missing required 'client' attribute for HTTP calls.")
    if not hasattr(context_with_client, "response"):
        context_with_client.response = None  # type: ignore # type: ResponseLike | None

    # Ensure context has 'locations' attribute for storing location ids
    if not hasattr(context_with_client, "locations"):
        context_with_client.locations = {}

    async def _run():
        location_id: str = context_with_client.locations[loc_name]  # type: ignore
        resp = await _post(context_with_client, "/api/v1/customers/", {
            "first_name": first,
            "last_name": last,
            "email": email,
            "phone": phone,
            "address": address,
            "location_id": location_id
        })
        assert resp.status_code == 200, resp.text
        context_with_client.customer = resp.json()
    anyio.run(_run)

@typed_given('an item exists titled "{title}" priced {price:f} with stock {stock:d}')
def step_create_item(context: Context, title: str, price: float, stock: int):
    # Cast context for type checking and attribute setup
    context_with_client = cast(ContextWithClient, context)
    if not hasattr(context_with_client, "items"):
        context_with_client.items = {} # type: ignore
    # Ensure context has 'items' attribute for storing item ids
    if not hasattr(context, "items"):
        context.items = {}
    async def _run():
        resp = await _post(context_with_client, "/api/v1/items/", {
            "title": title,
            "description": "",
            "price": price,
            "stock": stock
        })
        assert resp.status_code == 200, resp.text
        context_with_client.items[title] = resp.json()["id"]
    anyio.run(_run)

@typed_given('a drone exists model "{model}" serial "{serial}" payload {payload:f} range {range_km:f} at location "{loc_name}"')
def step_create_drone(context: Context, model: str, serial: str, payload: float, range_km: float, loc_name: str):
    context_with_client = cast(ContextWithClient, context)
    if not hasattr(context_with_client, "locations"):
        context_with_client.locations = {}
    # Ensure context has 'locations' attribute for storing location ids
    if not hasattr(context, "locations"):
        context.locations = {}
    async def _run():
        location_id = context_with_client.locations[loc_name]
        resp = await _post(context_with_client, "/api/v1/drones/", {
            "model": model,
            "serial_number": serial,
            "payload_capacity": payload,
            "range_km": range_km,
            "current_location_id": location_id
        })
        assert resp.status_code == 200, resp.text
        context_with_client.drone = resp.json()
    anyio.run(_run)

@typed_when('I place an order for customer "{email}" with items:')
def step_place_order(context: Context, email: str):
    context_with_client = cast(ContextWithClient, context)
    # Build items from table
    items: list[OrderLine] = []
    for row in context_with_client.table:
        item_title = row['item_title']
        quantity = int(row['quantity'])
        item_id = context_with_client.items[item_title]
        items.append({"item_id": item_id, "quantity": quantity})
        item_title = row['item_title']
        quantity = int(row['quantity'])
        item_id = context_with_client.items[item_title]
        items.append({"item_id": item_id, "quantity": quantity})

    async def _run():
        customer_id = context_with_client.customer["id"]
        resp = await _post(context_with_client, "/api/v1/orders/", {
            "customer_id": customer_id,
            "delivery_address": context_with_client.customer.get("address", ""),
            "items": items
        })
        assert resp.status_code == 200, resp.text
        context_with_client.order = resp.json()
    anyio.run(_run)

@typed_then('the order status should be "{status}"')
def step_assert_order_status(context: Context, status: str):
    context_with_client = cast(ContextWithClient, context)
    assert context_with_client.order["status"] == status, f"Expected {status}, got {context_with_client.order['status']}"

@typed_when('I create a delivery for the last order using drone "{serial}"')
@typed_then('I create a delivery for the last order using drone "{serial}"')
def step_create_delivery(context: Context, serial: str):
    context_with_client = cast(ContextWithClient, context)
    async def _run():
        order_id = context_with_client.order["id"]
        drone_id = context_with_client.drone["id"]
        # Use known start/destination from stored locations
        start_location_id = context_with_client.locations["Warehouse A"]
        destination_location_id = context_with_client.locations["Customer Home"]
        resp = await _post(context_with_client, "/api/v1/drones/deliveries/", {
            "order_id": order_id,
            "drone_id": drone_id,
            "start_location_id": start_location_id,
            "destination_location_id": destination_location_id
        })
        assert resp.status_code == 200, resp.text
        context_with_client.delivery = resp.json()
    anyio.run(_run)

@typed_then('I can fetch the delivery and it should exist')
def step_fetch_delivery(context: Context):
    context_with_client = cast(ContextWithClient, context)
    async def _run():
        delivery_id = context_with_client.delivery["id"]
        resp = await _get(context_with_client, f"/api/v1/drones/deliveries/{delivery_id}")
        assert resp.status_code == 200, resp.text
    anyio.run(_run)

@typed_when('I attempt to create a delivery for the last order using drone "{serial}"')
def step_attempt_create_delivery(context: Context, serial: str):
    context_with_client = cast(ContextWithClient, context)
    async def _run():
        order_id = context_with_client.order["id"]
        drone_id = context_with_client.drone["id"]
        # Use known start/destination from stored locations
        start_location_id = context_with_client.locations["Warehouse A"]
        destination_location_id = context_with_client.locations["Customer Home"]
        resp = await _post(context_with_client, "/api/v1/drones/deliveries/", {
            "order_id": order_id,
            "drone_id": drone_id,
            "start_location_id": start_location_id,
            "destination_location_id": destination_location_id
        })
        # Do not assert success; we expect failure in some scenarios
        # Keep the last response on the context for later assertions
        context_with_client.response = resp
    anyio.run(_run)

@typed_then('the last response should be {status:d} with message "{message}"')
def step_assert_last_response(context: Context, status: int, message: str):
    context_with_client = cast(ContextWithClient, context)
    resp = context_with_client.response
    assert resp is not None, "No response available to assert"
    assert resp.status_code == status, f"Expected status {status}, got {resp.status_code}: {resp.text}"
    data = resp.json()
    if isinstance(data, dict):
        data_dict: dict[str, Any] = data  # type: ignore
        detail_value = data_dict.get("detail")
        detail = str(detail_value) if detail_value is not None else None
    else:
        detail = None
    assert detail == message, f"Expected message '{message}', got '{detail}'"

@typed_when('I complete the last delivery')
@typed_then('I complete the last delivery')
def step_complete_last_delivery(context: Context):
    context_with_client = cast(ContextWithClient, context)
    async def _run():
        delivery_id = context_with_client.delivery["id"]
        resp = await _patch(context_with_client, f"/api/v1/drones/deliveries/{delivery_id}/complete")
        assert resp.status_code == 200, resp.text
    anyio.run(_run)

@typed_when('I set the drone "{serial}" status to "{status}"')
def step_set_drone_status(context: Context, serial: str, status: str):
    context_with_client = cast(ContextWithClient, context)
    async def _run():
        drone_id = context_with_client.drone["id"]
        # Ensure serial matches the known single drone assumption
        assert context_with_client.drone["serial_number"] == serial
        resp = await _patch(context_with_client, f"/api/v1/drones/{drone_id}/status", params={"status": status})
        assert resp.status_code == 200, resp.text
        context_with_client.drone = resp.json()
    anyio.run(_run)

@typed_then('the drone "{serial}" status should be "{status}"')
def step_assert_drone_status(context: Context, serial: str, status: str):
    context_with_client = cast(ContextWithClient, context)
    async def _run():
        drone_id = context_with_client.drone["id"]
        resp = await _get(context_with_client, f"/api/v1/drones/{drone_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["serial_number"] == serial, f"Expected serial {serial}, got {data['serial_number']}"
        assert data["status"] == status, f"Expected status {status}, got {data['status']}"
    anyio.run(_run)

@typed_when('I load cargo onto drone "{serial}" with item {item_id:d} quantity {quantity:d} weight {weight:f}')
def step_load_cargo(context: Context, serial: str, item_id: int, quantity: int, weight: float):
    context_with_client = cast(ContextWithClient, context)
    async def _run():
        drone_id = context_with_client.drone["id"]
        # Ensure serial matches the known single drone assumption
        assert context_with_client.drone["serial_number"] == serial
        resp = await _post(context_with_client, f"/api/v1/drones/{drone_id}/load", {
            "item_id": item_id,
            "quantity": quantity,
            "weight_kg": weight
        })
        assert resp.status_code == 200, resp.text
        context_with_client.drone = resp.json()
    anyio.run(_run)

@typed_when('I attempt to load cargo onto drone "{serial}" with item {item_id:d} quantity {quantity:d} weight {weight:f}')
def step_attempt_load_cargo(context: Context, serial: str, item_id: int, quantity: int, weight: float):
    context_with_client = cast(ContextWithClient, context)
    async def _run():
        drone_id = context_with_client.drone["id"]
        assert context_with_client.drone["serial_number"] == serial
        resp = await _post(context_with_client, f"/api/v1/drones/{drone_id}/load", {
            "item_id": item_id,
            "quantity": quantity,
            "weight_kg": weight
        })
        # Do not assert success; store response for later assertions
        context_with_client.response = resp
    anyio.run(_run)

@typed_when('I unload cargo from drone "{serial}" with item {item_id:d} quantity {quantity:d}')
def step_unload_cargo(context: Context, serial: str, item_id: int, quantity: int):
    context_with_client = cast(ContextWithClient, context)
    async def _run():
        drone_id = context_with_client.drone["id"]
        assert context_with_client.drone["serial_number"] == serial
        resp = await _post(context_with_client, f"/api/v1/drones/{drone_id}/unload", {
            "item_id": item_id,
            "quantity": quantity
        })
        assert resp.status_code == 200, resp.text
        context_with_client.drone = resp.json()
    anyio.run(_run)

@typed_then('the drone "{serial}" should have cargo weight {weight:f}')
def step_assert_drone_cargo_weight(context: Context, serial: str, weight: float):
    context_with_client = cast(ContextWithClient, context)
    async def _run():
        drone_id = context_with_client.drone["id"]
        resp = await _get(context_with_client, f"/api/v1/drones/{drone_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["serial_number"] == serial, f"Expected serial {serial}, got {data['serial_number']}"
        actual_weight = data.get("current_weight", 0.0)
        assert abs(actual_weight - weight) < 0.01, f"Expected cargo weight {weight}, got {actual_weight}"
    anyio.run(_run)

@typed_then('the last response should be {status:d} with message containing "{partial_message}"')
def step_assert_last_response_contains(context: Context, status: int, partial_message: str):
    context_with_client = cast(ContextWithClient, context)
    resp = context_with_client.response
    assert resp is not None, "No response available to assert"
    assert resp.status_code == status, f"Expected status {status}, got {resp.status_code}: {resp.text}"
    data = resp.json()
    if isinstance(data, dict):
        data_dict: dict[str, Any] = data  # type: ignore
        detail_value = data_dict.get("detail")
        detail = str(detail_value) if detail_value is not None else None
    else:
        detail = None
    assert detail is not None, f"Expected detail message containing '{partial_message}', but got no detail"
    assert partial_message in detail, f"Expected message containing '{partial_message}', got '{detail}'"
