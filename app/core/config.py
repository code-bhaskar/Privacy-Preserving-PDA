import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=os.path.join(BASE_DIR, ".env"), extra="ignore")

    APP_NAME: str = "PPDA"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # Comma-separated browser origins allowed to call the API. The Angular demo
    # frontend normally reaches the API through its own dev-server proxy
    # (frontend/proxy.conf.json), which is same-origin and needs no CORS entry;
    # this list matters when the SPA is opened directly (e.g. a built bundle or
    # a cloud preview host). "*" is accepted for demo deployments only.
    CORS_ORIGINS: str = "http://localhost:4200,http://127.0.0.1:4200"

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ppda"

    # Authentication — FR-1.2
    JWT_SECRET: str | None = None
    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # AES-GCM master key (base64, 32 bytes) — FR-15
    AES_MASTER_KEY: str | None = None

    # Federated learning defaults — FR-11..FR-14
    FL_CLIENT_COUNT: int = 5
    FL_LOCAL_EPOCHS: int = 3
    FL_ROUNDS: int = 5
    FL_CLIP_NORM: float = 1.0
    FL_DP_DELTA: float = 1e-5
    # How long POST /federated/round waits for real client processes to finish
    # their masked contributions before refusing the round.
    FL_ROUND_TIMEOUT_SECONDS: float = 240.0
    # Loopback URL the in-process coordinator is reachable at. Supervised FL
    # clients are spawned against this, which is what makes the whole federated
    # demo a single pipeline (one server, no separate coordinator process).
    FL_SERVER_URL: str = "http://127.0.0.1:8000"

    def get_jwt_secret(self) -> str | None:
        return self.JWT_SECRET or self.JWT_SECRET_KEY

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
