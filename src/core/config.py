from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn, AmqpDsn

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    
    # Caching
    CACHE_TTL: int = 60
    
    # Rate Limiting
    API_RATE_LIMIT_ENABLED: bool = True
    API_RATE_LIMIT_REQUESTS: int = 5
    API_RATE_LIMIT_WINDOW_SECONDS: int = 60
    
    # Security
    JWT_SECRET_KEY: str = "your-secret-key-for-dev-only"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
