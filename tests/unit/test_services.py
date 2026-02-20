import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from src.core.services import OrderService
from src.core.models import OrderCreate, OrderItemCreate
from src.data.models import Order

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def mock_producer():
    return AsyncMock()

@pytest.fixture
def mock_redis():
    return AsyncMock()

@pytest.fixture
def order_service(mock_db, mock_producer, mock_redis):
    return OrderService(mock_db, mock_producer, mock_redis)

@pytest.mark.asyncio
async def test_create_order_success(order_service, mock_db, mock_producer):
    # Arrange
    customer_id = uuid.uuid4()
    product_id = uuid.uuid4()
    order_in = OrderCreate(
        customer_id=customer_id,
        items=[OrderItemCreate(product_id=product_id, quantity=2)],
        shipping_address="123 Street"
    )
    
    # Act
    order = await order_service.create_order(order_in)
    
    # Assert
    assert order.customer_id == customer_id
    assert len(order.items) == 1
    assert order.total_amount == Decimal("100.00")  # 50.00 * 2
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_producer.publish_order_created.assert_called_once()

@pytest.mark.asyncio
async def test_get_order_from_cache(order_service, mock_redis):
    # Arrange
    order_id = str(uuid.uuid4())
    mock_redis.get_cached_order.return_value = {"order_id": order_id, "status": "PENDING"}
    
    # Act
    order = await order_service.get_order_by_id(order_id)
    
    # Assert
    assert order["order_id"] == order_id
    mock_redis.get_cached_order.assert_called_once_with(order_id)

@pytest.mark.asyncio
async def test_update_order_status_idempotent(order_service, mock_db):
    # Arrange
    order_id = str(uuid.uuid4())
    mock_order = MagicMock(spec=Order)
    mock_order.status = "PENDING"
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_order
    mock_db.execute.return_value = mock_result
    
    # Act: Update to same status
    await order_service.update_order_status(order_id, "PENDING")
    
    # Assert: No commit called
    mock_db.commit.assert_not_called()
    
    # Act: Update to new status
    await order_service.update_order_status(order_id, "PROCESSING")
    
    # Assert: Commit called
    assert mock_order.status == "PROCESSING"
    mock_db.commit.assert_called_once()
