"""Centralized configuration (M1). Everything environment-driven; dev defaults only."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='CVE_', env_file='.env', extra='ignore')

    # postgresql+psycopg2://user@/dbname?host=/socket/dir
    database_url: str = 'postgresql+psycopg2://postgres@/cve?host=/tmp/cve-pg'
    jwt_secret: str = 'dev-only-insecure-secret-change-me'
    jwt_ttl_seconds: int = 60 * 60 * 12
    upload_dir: str = '/tmp/cve-uploads'
    # DEV_MODE enables the demo persona quick-login buttons and the seed endpoint.
    # Never enable outside development/demo.
    dev_mode: bool = True
    cors_origins: str = 'http://localhost:5173,http://localhost:4173,http://localhost:4180'

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(',') if o.strip()]


settings = Settings()
