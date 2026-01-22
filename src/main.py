from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.api.routes import router
from src.messaging.consumer import consumer
from src.messaging.producer import producer
from src.caching.redis_client import redis_client
from src.data.database import engine, Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")
    
    # Create DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    await producer.connect()
    await consumer.connect() # Starts background consuming task
    await redis_client.connect()
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    await producer.close()
    await redis_client.close()
    # Consumer connection relies on persistent loop or separate handling
    if consumer.connection:
        await consumer.connection.close()

app = FastAPI(title="Order Processing Service", lifespan=lifespan)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    logger.error(f"Global exception: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"message": str(exc)},
    )

app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Order Processing Service is running"}
