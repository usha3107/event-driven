from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from src.core.models import OrderCreate, OrderResponse, OrderItemResponse
from src.data.database import get_db
from src.data.models import Order, OrderItem
from src.messaging.producer import get_producer, OrderEventProducer
from src.caching.redis_client import get_redis, RedisClient
from src.core.config import settings

router = APIRouter(prefix="/api/orders", tags=["orders"])

@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: Request,
    order_in: OrderCreate,
    db: AsyncSession = Depends(get_db),
    producer: OrderEventProducer = Depends(get_producer),
    redis: RedisClient = Depends(get_redis)
):
    # 1. Rate Limiting
    client_ip = request.client.host
    allowed = await redis.check_rate_limit(
        client_ip, 
        limit=settings.API_RATE_LIMIT_REQUESTS, 
        window=settings.API_RATE_LIMIT_WINDOW_SECONDS
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests"
        )

    # 2. Create Order in DB
    total_amount = 0
    db_items = []
    
    # Mocking price fetching logic
    mock_prices = {
        # UUIDs from example need to be handled, but for random UUIDs we just mock a price
        # In real app, we'd query Product Service
    }
    
    temp_total = 0
    for item in order_in.items:
        # Assign a mock price if not exists
        price = 50.00 
        temp_total += price * item.quantity
        
        db_item = OrderItem(
            product_id=item.product_id,
            quantity=item.quantity,
            price=price
        )
        db_items.append(db_item)
    
    new_order = Order(
        customer_id=order_in.customer_id,
        shipping_address=order_in.shipping_address,
        total_amount=temp_total,
        status="PENDING",
        items=db_items
    )
    
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)

    # 3. Publish Event
    order_data = {
        "order_id": new_order.order_id,
        "customer_id": new_order.customer_id,
        "items": [
            {"product_id": i.product_id, "quantity": i.quantity, "price": float(i.price)} 
            for i in new_order.items
        ],
        "total_amount": float(new_order.total_amount)
    }
    
    await producer.publish_order_created(order_data)
    
    return new_order

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str, # UUID as string
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    # 1. Check Cache
    cached_order = await redis.get_cached_order(order_id)
    if cached_order:
        return cached_order

    # 2. Fetch from DB
    try:
        # UUID validation
        stmt = select(Order).where(Order.order_id == order_id)
        result = await db.execute(stmt)
        order = result.scalar_one_or_none()
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid UUID format")

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # 3. Cache Result (serialize response model)
    # We need to serialize the SQLAlchemy model to a dict compatible with Pydantic/JSON
    # Using Pydantic model's dump method if available, or manual construction
    
    response_model = OrderResponse.model_validate(order)
    order_dict = json.loads(response_model.model_dump_json())
    
    await redis.set_cached_order(str(order.order_id), order_dict, ttl=60)

    return order

import json
