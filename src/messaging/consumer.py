import json
import logging
import asyncio
import aio_pika
from sqlalchemy import update
from sqlalchemy.future import select
from src.core.config import settings
from src.data.database import AsyncSessionLocal
from src.data.models import Order

logger = logging.getLogger(__name__)

class PaymentEventConsumer:
    def __init__(self):
        self.connection = None

    async def connect(self):
        try:
            self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            channel = await self.connection.channel()
            exchange = await channel.declare_exchange(
                "payments", aio_pika.ExchangeType.TOPIC, durable=True
            )
            queue = await channel.declare_queue("payment_updates", durable=True)
            await queue.bind(exchange, routing_key="payment.processed")
            
            # Start consuming
            await queue.consume(self.process_message)
            logger.info("Listening for PaymentProcessed events...")
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ consumer: {e}")
            # Retry logic could be added here

    async def process_message(self, message: aio_pika.IncomingMessage):
        async with message.process():
            try:
                body = json.loads(message.body)
                event_type = body.get("event_type")
                if event_type == "PaymentProcessed":
                    payload = body.get("payload", {})
                    order_id = payload.get("order_id")
                    payment_status = payload.get("payment_status")
                    
                    if order_id and payment_status:
                        await self.update_order_status(order_id, payment_status)
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    async def update_order_status(self, order_id: str, payment_status: str):
        new_status = "PROCESSING" if payment_status == "SUCCESS" else "FAILED"
        
        async with AsyncSessionLocal() as session:
            try:
                # Can use UUID directly if string format matches
                stmt = select(Order).where(Order.order_id == order_id)
                result = await session.execute(stmt)
                order = result.scalar_one_or_none()
                
                if order:
                    order.status = new_status
                    await session.commit()
                    logger.info(f"Updated order {order_id} status to {new_status}")
                else:
                    logger.warning(f"Order {order_id} not found for status update")
            except Exception as e:
                logger.error(f"Failed to update order status in DB: {e}")
                await session.rollback()

consumer = PaymentEventConsumer()
