import pytest
import httpx
import uuid
import asyncio
from src.main import app

import pytest
import httpx
import uuid
from src.main import app
from src.core.security import create_access_token
from src.messaging.producer import get_producer
from src.caching.redis_client import get_redis
from src.data.database import get_db
from unittest.mock import AsyncMock

# Mock dependencies
mock_db = AsyncMock()
mock_redis = AsyncMock()
mock_producer = AsyncMock()

@pytest.fixture
def auth_header():
    token = create_access_token(data={"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_order_full_flow_functional(auth_header):
    # Setup overrides
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_producer] = lambda: mock_producer
    
    mock_redis.check_rate_limit.return_value = True
    
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        customer_id = str(uuid.uuid4())
        payload = {
            "customer_id": customer_id,
            "items": [{"product_id": str(uuid.uuid4()), "quantity": 1}],
            "shipping_address": "Test Address"
        }
        
        # 1. Create Order (Authenticated)
        response = await client.post("/api/orders/", json=payload, headers=auth_header)
        assert response.status_code == 201
        order_id = response.json()["order_id"]
        
        # Verify background task would have been called (simplified check)
        mock_producer.publish_order_created.assert_called()

        # 2. Get Order
        mock_redis.get_cached_order.return_value = None
        # Mock DB response for get_order
        mock_order = AsyncMock()
        mock_order.order_id = order_id
        mock_order.customer_id = customer_id
        mock_order.status = "PENDING"
        mock_order.total_amount = 50.0
        mock_order.items = []
        
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        response = await client.get(f"/api/orders/{order_id}", headers=auth_header)
        assert response.status_code == 200
        assert response.json()["order_id"] == order_id

    # Clean up overrides
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_unauthorized_access():
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/orders/some-id")
        assert response.status_code == 401
