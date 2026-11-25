"""Runtime settings, read from SENTINEL_GEN_* environment variables."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTINEL_GEN_")

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "atlas"
    db_user: str = "postgres"
    db_password: SecretStr
    metrics_port: int = 8094

    def conninfo(self) -> str:
        """libpq connection parameters; the password is passed separately, never logged."""
        return f"host={self.db_host} port={self.db_port} dbname={self.db_name} user={self.db_user}"
