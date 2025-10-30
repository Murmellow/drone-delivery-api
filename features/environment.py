# Behave environment: set up an in-process HTTP client for the FastAPI app
import os
import sys
from typing import Any

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Set test environment variables before importing app
os.environ["USE_CQRS"] = "true"
# Ensure AWS_SQS_QUEUE_URL is not set for local testing
if "AWS_SQS_QUEUE_URL" in os.environ:
    del os.environ["AWS_SQS_QUEUE_URL"]

from app.main import app  # noqa: E402
from app.core.database import Base, engine  # noqa: E402
from app.services.local_bus import local_bus  # noqa: E402
from app.services.outbox_publisher import publisher  # noqa: E402
import httpx  # noqa: E402
import anyio  # noqa: E402

client: httpx.AsyncClient | None = None


def before_all(context: Any) -> None:
    global client
    # Ensure database schema exists at start
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Start local bus and outbox publisher for CQRS tests
    local_bus.start()
    publisher.start()
    
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    context.client = client

def before_scenario(context: Any, scenario: Any) -> None:
    # Isolate each scenario with a clean database
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def after_all(context: Any) -> None:
    global client
    # Stop local bus and publisher
    local_bus.stop()
    publisher.stop()
    
    if client is not None:
        # Close async client cleanly
        anyio.run(client.aclose)
        client = None
