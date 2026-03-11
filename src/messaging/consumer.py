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
            
            # Declare Dead Letter Exchange (DLX) and Dead Letter Queue (DLQ)
            dlx_exchange = await channel.declare_exchange(
                "dlx.payments", aio_pika.ExchangeType.FANOUT, durable=True
            )
            dlq = await channel.declare_queue("payment_updates.dlq", durable=True)
            await dlq.bind(dlx_exchange, routing_key="#")
            
            # Declare main exchange
            exchange = await channel.declare_exchange(
                "payments", aio_pika.ExchangeType.TOPIC, durable=True
            )
            
            # Declare main queue with DLX configuration
            queue = await channel.declare_queue(
                "payment_updates", 
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "dlx.payments",
                    "x-dead-letter-routing-key": "#"
                }
            )
            await queue.bind(exchange, routing_key="payment.processed")
            
            await queue.consume(self.process_message)
            logger.info("Listening for PaymentProcessed events with DLQ enabled...")
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ consumer: {e}")


    async def process_message(self, message: aio_pika.IncomingMessage):
        try:
            body = json.loads(message.body)
            event_type = body.get("event_type")
            if event_type == "PaymentProcessed":
                payload = body.get("payload", {})
                order_id = payload.get("order_id")
                payment_status = payload.get("payment_status")
                
                if order_id and payment_status:
                    new_status = "PROCESSING" if payment_status == "SUCCESS" else "FAILED"
                    async with AsyncSessionLocal() as session:
                        from src.messaging.producer import producer
                        from src.caching.redis_client import redis_client
                        from src.core.services import OrderService
                        
                        service = OrderService(session, producer, redis_client)
                        await service.update_order_status(order_id, new_status)
            
            await message.ack()
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # On error, we nack without requeueing to send to DLQ (if configured)
            await message.nack(requeue=False)

consumer = PaymentEventConsumer()
