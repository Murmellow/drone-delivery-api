from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routers import items, customers, orders, drones, locations
from app.routers import demo
from app.core.config import settings
from app.core.database import Base, engine
# Import models so that SQLAlchemy is aware of them before creating tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all tables are created before serving requests (useful for tests)
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="Drone Delivery API",
    version=settings.VERSION,
    description="API for managing customers, items, orders, and drone deliveries",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
# Startup is handled by the lifespan context; no on_event hook needed.

# Include API routers
app.include_router(items.router, prefix=settings.API_V1_STR)
app.include_router(customers.router, prefix=settings.API_V1_STR)
app.include_router(orders.router, prefix=settings.API_V1_STR)
app.include_router(drones.router, prefix=settings.API_V1_STR)
app.include_router(locations.router, prefix=settings.API_V1_STR)
app.include_router(demo.router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI!"}