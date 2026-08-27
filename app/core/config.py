import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=os.path.join(BASE_DIR, ".env"), extra="ignore")

    APP_NAME: str = "PPDA"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ppda"

    # Authentication — FR-1.2
    JWT_SECRET: str = "supersecretjwtkeyforppdadevelopmentonly1234567890"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # AES-GCM master key (base64, 32 bytes) — FR-15
    AES_MASTER_KEY: str = "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdoaWo="

    # Federated learning defaults — FR-11..FR-14
    FL_CLIENT_COUNT: int = 5
    FL_LOCAL_EPOCHS: int = 3
    FL_ROUNDS: int = 5
    FL_CLIP_NORM: float = 1.0
    FL_DP_DELTA: float = 1e-5


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
