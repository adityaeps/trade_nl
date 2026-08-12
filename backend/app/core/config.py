from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    encryption_key: str
    cors_origins: str = "http://localhost:3000"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, v: str) -> str:
        """Normalises a plain `postgresql://` URL to `postgresql+psycopg://`.

        Managed providers (Neon, Render, Heroku) hand out `postgresql://`
        (and Heroku still emits the legacy `postgres://`), but this app is
        pinned to psycopg 3, which SQLAlchemy only selects when the driver
        is named explicitly - otherwise it reaches for psycopg2, which
        isn't installed, and the app dies at startup with a confusing
        ModuleNotFoundError. Normalising here means the provider's copy-
        pasted connection string just works.
        """
        if v.startswith("postgres://"):
            v = "postgresql://" + v.removeprefix("postgres://")
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v.removeprefix("postgresql://")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()
