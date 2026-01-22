from pydantic import BaseModel, Field
from uuid import UUID
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

class OrderItemBase(BaseModel):
    product_id: UUID
    quantity: int = Field(gt=0)
    # Price is not in request, should be fetched from Product Service (mocked here)

class OrderItemCreate(OrderItemBase):
    pass

class OrderItemResponse(OrderItemBase):
    price: Decimal

    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    customer_id: UUID
    items: List[OrderItemCreate]
    shipping_address: str

class OrderResponse(BaseModel):
    order_id: UUID
    customer_id: UUID
    items: List[OrderItemResponse]
    shipping_address: str
    status: str
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
