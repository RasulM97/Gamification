"""Centralized configuration (M1). Everything environment-driven; dev defaults only."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='CVE_', env_file='.env', extra='ignore')

    # postgresql+psycopg2://user@/dbname?host=/socket/dir
    database_url: str = 'postgresql+psycopg2://postgres@/cve?host=/tmp/cve-pg'
    jwt_secret: str = 'dev-only-insecure-secret-change-me'
    jwt_ttl_seconds: int = 60 * 60 * 12
    # Independent 32-byte operator key (64 hex characters); empty disables webhook ingress.
    webhook_master_key: str = Field(default='', repr=False)
    upload_dir: str = '/tmp/cve-uploads'
    # DEV_MODE enables the demo persona quick-login buttons and the seed endpoint.
    # Never enable outside development/demo.
    dev_mode: bool = False
    allow_weak_dev_passwords: bool = False
    cors_origins: str = 'http://localhost:5173,http://localhost:4173,http://localhost:4180'

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(',') if o.strip()]

    # WS1 outbound delivery (email). Empty smtp_host disables sending —
    # outbox rows stay PENDING and inspectable; the product remains honest
    # about the delivery limitation instead of pretending delivery happened.
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = Field(default='', repr=False)
    smtp_from: str = 'cve@localhost'
    smtp_starttls: bool = True
    # Absolute base used in outbound messages so recipients can open CVE.
    public_base_url: str = 'http://localhost:4180'
    # Help escalation window (minutes). Bounded: 15 minutes … 7 days.
    help_escalation_minutes: int = 240

    @property
    def help_escalation_window_ms(self) -> float:
        minutes = min(max(self.help_escalation_minutes, 15), 10080)
        return minutes * 60 * 1000


settings = Settings()
