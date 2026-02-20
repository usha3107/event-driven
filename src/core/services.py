import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status

from src.core.models import OrderCreate, OrderResponse
from src.data.models import Order, OrderItem
from src.messaging.producer import OrderEventProducer
from src.caching.redis_client import RedisClient

logger = logging.getLogger(__name__)

class OrderService:
    def __init__(self, db: AsyncSession, producer: OrderEventProducer, redis: RedisClient):
        self.db = db
        self.producer = producer
        self.redis = redis

    async def create_order(self, order_in: OrderCreate) -> Order:
        temp_total = 0
        db_items = []
        
        for item in order_in.items:
            price = 50.00  # Default mock price
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
        
        try:
            self.db.add(new_order)
            await self.db.commit()
            await self.db.refresh(new_order)
            
            # Prepare event data
            order_data = {
                "order_id": str(new_order.order_id),
                "customer_id": str(new_order.customer_id),
                "items": [
                    {"product_id": str(i.product_id), "quantity": i.quantity, "price": float(i.price)} 
                    for i in new_order.items
                ],
                "total_amount": float(new_order.total_amount)
            }
            
            # Publish event
            await self.producer.publish_order_created(order_data)
            logger.info(f"Order {new_order.order_id} created and event published.")
            
            return new_order
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create order: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create order"
            )

    async def get_order_by_id(self, order_id: str) -> Order:
        # Check cache first
        cached_order = await self.redis.get_cached_order(order_id)
        if cached_order:
            return cached_order

        # Database lookup
        try:
            stmt = select(Order).where(Order.order_id == order_id)
            result = await self.db.execute(stmt)
            order = result.scalar_one_or_none()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid UUID format")

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        from src.core.models import OrderResponse
        import json
        
        response_data = OrderResponse.model_validate(order)
        order_dict = json.loads(response_data.model_dump_json())
        await self.redis.set_cached_order(str(order.order_id), order_dict, ttl=60)
        
        return order

    async def update_order_status(self, order_id: str, new_status: str):
        try:
            stmt = select(Order).where(Order.order_id == order_id)
            result = await self.db.execute(stmt)
            order = result.scalar_one_or_none()
            
            if order:
                # Idempotency check: only update if status is different
                if order.status != new_status:
                    order.status = new_status
                    await self.db.commit()
                    logger.info(f"Updated order {order_id} status to {new_status}")
            else:
                logger.warning(f"Order {order_id} not found for status update")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update order status: {e}")
