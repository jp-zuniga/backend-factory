from collections.abc import Sequence
from datetime import timedelta
from functools import cached_property
from typing import Annotated, Final, Literal, Self
from urllib.parse import unquote

from psycopg import IsolationLevel
from pydantic import (
    HttpUrl,
    NonNegativeInt,
    PositiveInt,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    StringConstraints,
    model_validator,
)
from pydantic_core import MultiHostHost
from pydantic_settings import BaseSettings, SettingsConfigDict

from api_core.schemas.base import PermissiveDTO
from api_utils.env import ROOT

########################################################################################

MAX_SECRET_LENGTH: Final[int] = 256
MIN_SECRET_LENGTH: Final[int] = 64

type LongSecret = Annotated[
    SecretStr,
    StringConstraints(max_length=MAX_SECRET_LENGTH, min_length=MIN_SECRET_LENGTH),
]

type OptionalSecret = Annotated[
    SecretStr,
    StringConstraints(max_length=MAX_SECRET_LENGTH),
]

########################################################################################


class ApiConfig(BaseSettings, PermissiveDTO):
    model_config = SettingsConfigDict(
        enable_decoding=False,
        env_file=(ROOT / ".env"),
        env_file_encoding="utf-8",
        validate_default=True,
    )

    DEBUG: bool = False
    DEPLOY: bool = False
    SKIP_SEEDERS: bool = False

    JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"

    JWT_ACCESS_LIFETIME: timedelta = timedelta(hours=3)
    JWT_CHALLENGE_LIFETIME: timedelta = timedelta(minutes=5)
    JWT_REFRESH_LIFETIME: timedelta = timedelta(days=1)

    TOTP_DIGITS: Literal[6, 8] = 6
    TOTP_ISSUER: Annotated[
        str,
        StringConstraints(max_length=64, min_length=1),
    ] = "api"

    TOTP_LOCKOUT: timedelta = timedelta(minutes=15)
    TOTP_MAX_FAILURES: PositiveInt = 5
    TOTP_PERIOD: PositiveInt = 30
    TOTP_RECOVERY_CODES: PositiveInt = 10
    TOTP_TOLERANCE: NonNegativeInt = 1

    DEFAULT_FROM_EMAIL: str = "no-reply@localhost"
    EMAIL_BACKEND: str = "django.core.mail.backends.console.EmailBackend"
    EMAIL_HOST: str = ""
    EMAIL_HOST_PASSWORD: OptionalSecret = SecretStr(secret_value="")
    EMAIL_HOST_USER: str = ""
    EMAIL_PORT: PositiveInt = 587
    EMAIL_USE_TLS: bool = True

    EMAIL_VERIFICATION_LIFETIME: timedelta = timedelta(hours=24)
    REQUIRE_EMAIL_VERIFICATION: bool = True

    FRONTEND_URL: HttpUrl = HttpUrl(url="http://localhost:3000")

    DATABASE_URL: PostgresDsn
    REDIS_URL: RedisDsn

    JWT_SECRET_KEY: LongSecret
    SECRET_KEY: LongSecret

    REDIS_SECRET_KEY: OptionalSecret = SecretStr(secret_value="")

    @model_validator(mode="after")
    def check_cookie_policy(self) -> Self:
        if self.cookie_samesite == "None" and not self.cookie_secure:
            raise ValueError("`SameSite=None` requiere `Secure`.")

        return self

    @model_validator(mode="after")
    def check_database_url(self) -> Self:
        if self.DATABASE_URL.path is None:
            raise ValueError(
                "`DATABASE_URL` no define el nombre de la base de datos en `path`.",
            )
        if len(self.DATABASE_URL.hosts()) > 1:
            raise ValueError("`DATABASE_URL` debería tener un único host.")

        host = self.pg_host

        if host["host"] is None:
            raise ValueError("`DATABASE_URL` no define el host de la base de datos.")
        if host["username"] is None:
            raise ValueError("`DATABASE_URL` no define un usuario.")
        if host["password"] is None:
            raise ValueError("`DATABASE_URL` no define una contraseña.")

        return self

    @model_validator(mode="after")
    def check_email_delivery(self) -> Self:
        if not self.DEPLOY:
            return self

        missing: Sequence[str] = tuple(
            name
            for name in ("DEFAULT_FROM_EMAIL", "EMAIL_HOST")
            if not getattr(self, name)
        )

        if missing:
            raise ValueError(
                f"{', '.join(f'`{name}`' for name in missing)} "
                "es obligatorio cuando `DEPLOY=True`.",
            )

        return self

    @model_validator(mode="after")
    def check_lifetimes(self) -> Self:
        expired: Sequence[str] = tuple(
            name
            for name in (
                "EMAIL_VERIFICATION_LIFETIME",
                "JWT_ACCESS_LIFETIME",
                "JWT_CHALLENGE_LIFETIME",
                "JWT_REFRESH_LIFETIME",
            )
            if getattr(self, name) <= timedelta()
        )

        if expired:
            raise ValueError(
                f"{', '.join(f'`{name}`' for name in expired)} "
                "debe ser una duración positiva.",
            )

        return self

    @model_validator(mode="after")
    def check_redis_secret_key(self) -> Self:
        if (
            self.DEPLOY
            and len(self.REDIS_SECRET_KEY.get_secret_value()) < MIN_SECRET_LENGTH
        ):
            raise ValueError(
                "`REDIS_SECRET_KEY` es obligatorio; "
                f"debe tener al menos {MIN_SECRET_LENGTH} "
                "caracteres cuando `DEPLOY=True`.",
            )

        return self

    @cached_property
    def cookie_samesite(self) -> Literal["Lax", "None"]:
        return "Lax" if self.DEBUG and not self.DEPLOY else "None"

    @cached_property
    def cookie_samesite_policy(self) -> Literal["lax", "none"]:
        """
        `cookie_samesite`, spelled the way `dmr.cookies.CookieSpec` wants it.

        Django writes the flag verbatim and browsers match it
        case-insensitively, but `CookieSpec` compares the value it
        describes against the one we set, so the two must agree exactly.
        """

        return "lax" if self.cookie_samesite == "Lax" else "none"

    @cached_property
    def cookie_secure(self) -> bool:
        return not self.DEBUG or self.DEPLOY

    @cached_property
    def csrf_cookie_name(self) -> str:
        return "csrftoken"

    @cached_property
    def csrf_header(self) -> str:
        return f"x-{self.csrf_cookie_name}"

    @cached_property
    def frontend_url(self) -> str:
        return str(self.FRONTEND_URL).rstrip("/")

    @cached_property
    def pg_database(self) -> dict:
        return {
            "ATOMIC_REQUESTS": False,
            "CONN_HEALTH_CHECKS": True,
            "ENGINE": "django.db.backends.postgresql",
            "HOST": unquote(
                errors="strict",
                string=self.pg_host["host"] or "",
            ),
            "NAME": unquote(
                errors="strict",
                string=(self.DATABASE_URL.path or "").removeprefix("/"),
            ),
            "PASSWORD": unquote(
                errors="strict",
                string=self.pg_host["password"] or "",
            ),
            "PORT": self.pg_host["port"] or 5432,
            "OPTIONS": {
                "client_encoding": "utf-8",
                "isolation_level": IsolationLevel.READ_COMMITTED,
                "pool": True,
            },
            "USER": unquote(
                errors="strict",
                string=self.pg_host["username"] or "",
            ),
        }

    @cached_property
    def pg_host(self) -> MultiHostHost:
        return self.DATABASE_URL.hosts()[0]

    @cached_property
    def redis_cache(self) -> dict:
        cache: dict = {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": unquote(
                errors="strict",
                string=f"redis://{self.REDIS_URL.host}:{self.REDIS_URL.port or 6379}",
            ),
        }

        password = self.REDIS_SECRET_KEY.get_secret_value()

        if password:
            cache["OPTIONS"] = {
                "password": unquote(errors="strict", string=password),
                "username": unquote(
                    errors="strict",
                    string=self.REDIS_URL.username or "default",
                ),
            }

        return cache


########################################################################################

CONFIG: Final[ApiConfig] = ApiConfig()
