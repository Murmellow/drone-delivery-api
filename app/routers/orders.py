from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import order as models, item as item_models, customer as customer_models
from app.schemas import order as schemas
from datetime import datetime, timezone

router = APIRouter(prefix="/orders", tags=["orders"])
orders_to_be_delivered: list[schemas.OrderCreate] = []
        
async def add_order(order: schemas.OrderCreate, db: Session) -> dict[str, str]:
    orders_to_be_delivered.append(order)
    if len(orders_to_be_delivered) == 1:
        await process_order_queue(db)
    return {"message": "Order added to queue"}

async def process_order_queue(db: Session) -> None:
    while orders_to_be_delivered:
        order: schemas.OrderCreate = orders_to_be_delivered.pop(0)
        # Process the order
        await create_order(order, db)

@router.post("/", response_model=schemas.Order)
async def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db)) -> models.Order:
    # Calculate total amount and verify stock
    total_amount = 0
    order_items: list[models.OrderItem] = []
    
    for item_order in order.items:
        item: item_models.Item | None = db.query(item_models.Item).filter(item_models.Item.id == item_order.item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {item_order.item_id} not found")
        if int(getattr(item, "stock")) < int(item_order.quantity):
            raise HTTPException(status_code=400, detail=f"Not enough stock for item {item.title}")
        
        # Update stock
        setattr(item, "stock", int(getattr(item, "stock")) - int(item_order.quantity))
        total_amount += item.price * item_order.quantity
        
        order_items.append(models.OrderItem(
            item_id=item.id,
            quantity=item_order.quantity,
            unit_price=item.price
        ))
    
    # Resolve customer's delivery location
    customer: customer_models.Customer | None = db.query(customer_models.Customer).filter(customer_models.Customer.id == order.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Create order
    db_order = models.Order(
        customer_id=order.customer_id,
        total_amount=total_amount,
        status=models.OrderStatus.PENDING.value,
        items=order_items,
        delivery_address=order.delivery_address,
        delivery_location_id=customer.location_id
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    
    return db_order

@router.get("/", response_model=list[schemas.Order])
def read_orders(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)) -> list[models.Order]:
    orders: list[models.Order] = db.query(models.Order).offset(skip).limit(limit).all()
    return orders

@router.get("/{order_id}", response_model=schemas.Order)
def read_order(order_id: int, db: Session = Depends(get_db)) -> models.Order:
    order: models.Order | None = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.patch("/{order_id}/status", response_model=schemas.Order)
async def update_order_status(order_id: int, status: str, db: Session = Depends(get_db)) -> models.Order:
    order: models.Order | None = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    
    valid_statuses: list[str] = ["pending", "processing", "shipped", "delivered", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {valid_statuses}")
    
    setattr(order, "status", status)
    order.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(order)
    return order