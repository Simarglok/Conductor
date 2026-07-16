from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CONDUCTOR_",
    )

    # ── Database ──
    database_url: str = "postgresql+asyncpg://conductor:conductor@postgres:5432/conductor"

    # ── Redis ──
    redis_url: str = "redis://redis:6379/0"

    # ── Auth ──
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    redis_refresh_prefix: str = "refresh_token:"

    # ── Seed admin ──
    admin_email: str = "admin@conductor.local"
    admin_password: str = "admin"
    admin_name: str = "Admin"

    # ── Airflow (will be wired later) ──
    airflow_base_url: str = "http://airflow-api-server:8080"

    # ── Workspace (code-server) ──
    code_server_host: str = "http://code-server:8080"
    code_server_jwt_secret: str = "conductor-cs-jwt-secret-change-in-prod"


settings = Settings()
