import json
import logging
from datetime import datetime
import aio_pika
from src.core.config import settings

logger = logging.getLogger(__name__)

class OrderEventProducer:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.exchange = None

    async def connect(self):
        if not self.connection:
            try:
                self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
                self.channel = await self.connection.channel()
                self.exchange = await self.channel.declare_exchange(
                    "orders", aio_pika.ExchangeType.TOPIC, durable=True
                )
                logger.info("Connected to RabbitMQ for producing.")
            except Exception as e:
                logger.error(f"Failed to connect to RabbitMQ producer: {e}")
                raise

    async def close(self):
        if self.connection:
            await self.connection.close()

    async def publish_order_created(self, order_data: dict):
        if not self.exchange:
            await self.connect()

        event = {
            "event_type": "OrderCreated",
            "event_id": str(order_data.get("order_id")), # Using order_id as unique event id for simplicity or gen new one
            "timestamp": datetime.utcnow().isoformat(),
            "payload": order_data
        }

        message = aio_pika.Message(
            body=json.dumps(event, default=str).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        await self.exchange.publish(message, routing_key="order.created")
        logger.info(f"Published OrderCreated event for order {order_data.get('order_id')}")

producer = OrderEventProducer()

async def get_producer():
    if not producer.connection:
        await producer.connect()
    return producer
