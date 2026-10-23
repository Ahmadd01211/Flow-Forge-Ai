from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    session_signing_key: str = Field(min_length=32)
    public_origin: str = "http://localhost:8080"
    credential_key_path: str = "/run/secrets/flowforge-credentials.key"
    mcp_catalog_json: str = "[]"
    secure_cookies: bool = False
    session_idle_hours: int = 12
    session_absolute_hours: int = 168
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    mail_from: str = "FlowForge <no-reply@flowforge.local>"

    @property
    def session_cookie(self) -> str:
        return "__Host-ff_session" if self.secure_cookies else "ff_session_dev"

    @property
    def preauth_cookie(self) -> str:
        return "__Host-ff_preauth" if self.secure_cookies else "ff_preauth_dev"
