from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str = Field(..., alias="BOT_TOKEN")
    DB_HOST: str = Field(..., alias="DB_HOST")
    DB_PORT: int = Field(..., alias="DB_PORT")
    DB_USER: str = Field(..., alias="DB_USER")
    DB_PASS: str = Field(..., alias="DB_PASS")
    DB_NAME: str = Field(..., alias="DB_NAME")
    GOOGLE_BOOKS_API_KEY: str | None = Field(default=None, alias="GOOGLE_BOOKS_API_KEY")
    TIMEZONE: str = Field(default="Europe/Madrid", alias="TIMEZONE")
    GROUP_CHAT_ID: int | None = Field(default=None, alias="GROUP_CHAT_ID")
    PUBLIC_BASE_URL: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    CALENDAR_HTTP_PORT: int = Field(default=8080, alias="CALENDAR_HTTP_PORT")
    DEBUG: bool = Field(default=False, alias="DEBUG")

    @field_validator("GROUP_CHAT_ID", mode="before")
    @classmethod
    def empty_group_chat_id(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("PUBLIC_BASE_URL", mode="before")
    @classmethod
    def empty_public_base_url(cls, value: object) -> object:
        if value == "":
            return None
        if isinstance(value, str):
            return value.rstrip("/")
        return value

    @property
    def async_pg_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:"
            f"{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def admin_ids(self) -> frozenset[int]:
        return frozenset()


@lru_cache
def get_settings() -> Settings:
    return Settings()
