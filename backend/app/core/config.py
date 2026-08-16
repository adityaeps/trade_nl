import sys

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# What each required setting is for, and how to produce one. Printed when
# the app can't start for want of it - a deploy that dies on a missing
# variable otherwise surfaces as a pydantic traceback several imports deep
# (alembic -> models -> crypto -> config), which says nothing about what to
# actually go and set.
_SETTING_HELP = {
    "database_url": (
        "Postgres connection string. On Render this is wired in from the "
        "database declared in render.yaml; locally it goes in backend/.env."
    ),
    "jwt_secret": (
        "Signs admin login tokens. Any long random string; safe to rotate "
        "(it only signs out active admin sessions). Generate with:\n"
        '      python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
    ),
    "encryption_key": (
        "Encrypts payouts.iban. MUST stay stable for the life of the "
        "database - rotating it makes every stored IBAN permanently "
        "unreadable. Generate once, then store it in a password manager:\n"
        '      python3 -c "import base64, os; '
        'print(base64.urlsafe_b64encode(os.urandom(32)).decode())"'
    ),
}


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


def _load_settings() -> Settings:
    """Builds Settings, turning a missing-variable failure into something
    you can act on without reading a traceback."""
    try:
        return Settings()
    except ValidationError as e:
        missing = [
            str(err["loc"][0]) for err in e.errors() if err["type"] == "missing"
        ]
        if not missing:
            raise
        lines = [
            "",
            "Cannot start: required environment variable(s) not set.",
            "",
        ]
        for name in missing:
            lines.append(f"  {name.upper()}")
            help_text = _SETTING_HELP.get(name)
            if help_text:
                lines.append(f"      {help_text}")
            lines.append("")
        lines.append(
            "Set these in backend/.env locally, or in your host's environment "
            "settings when deployed (on Render: your service -> Environment -> "
            "Add Environment Variable). See DEPLOY.md."
        )
        lines.append("")
        print("\n".join(lines), file=sys.stderr)
        raise SystemExit(1) from None


settings = _load_settings()
