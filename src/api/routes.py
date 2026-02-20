from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from src.core.models import OrderCreate, OrderResponse
from src.data.database import get_db
from src.messaging.producer import get_producer, OrderEventProducer
from src.caching.redis_client import get_redis, RedisClient
from src.core.config import settings
from src.core.services import OrderService

router = APIRouter(prefix="/api/orders", tags=["orders"])

async def get_order_service(
    db: AsyncSession = Depends(get_db),
    producer: OrderEventProducer = Depends(get_producer),
    redis: RedisClient = Depends(get_redis)
) -> OrderService:
    return OrderService(db, producer, redis)

@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: Request,
    order_in: OrderCreate,
    redis: RedisClient = Depends(get_redis),
    service: OrderService = Depends(get_order_service)
):
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

    return await service.create_order(order_in)

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    service: OrderService = Depends(get_order_service)
):
    return await service.get_order_by_id(order_id)
