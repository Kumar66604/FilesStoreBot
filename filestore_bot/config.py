"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int_list(name: str) -> list[int]:
    return [int(value.strip()) for value in os.environ.get(name, "").split(",") if value.strip()]


@dataclass(frozen=True, slots=True)
class Settings:
    api_id: int
    api_hash: str
    bot_token: str
    workers: int
    db_uri: str
    db_name: str
    db_channel: int
    admins: list[int]
    auto_delete_seconds: int
    protect_content: bool
    port: int
    free_files: int
    subscription_stars: int
    subscription_days: int
    upi_id: str
    upi_amount: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_id=int(os.environ.get("API_ID", "0")),
            api_hash=os.environ.get("API_HASH", ""),
            bot_token=os.environ.get("BOT_TOKEN", ""),
            workers=int(os.environ.get("WORKERS", "5")),
            db_uri=os.environ.get("DB_URI", "mongodb://localhost:27017"),
            db_name=os.environ.get("DB_NAME", "filestore"),
            db_channel=int(os.environ.get("DB_CHANNEL", "0")),
            admins=_env_int_list("ADMINS"),
            auto_delete_seconds=int(os.environ.get("AUTO_DEL", "300")),
            protect_content=_env_bool("PROTECT", True),
            port=int(os.environ.get("PORT", "10000")),
            free_files=int(os.environ.get("FREE_FILES", "3")),
            subscription_stars=int(os.environ.get("SUBSCRIPTION_STARS", "100")),
            subscription_days=int(os.environ.get("SUBSCRIPTION_DAYS", "30")),
            upi_id=os.environ.get("UPI_ID", "").strip(),
            upi_amount=os.environ.get("UPI_AMOUNT", "99").strip(),
        )

    def validate(self) -> None:
        missing = [
            name
            for name, value in {
                "API_ID": self.api_id,
                "API_HASH": self.api_hash,
                "BOT_TOKEN": self.bot_token,
                "DB_CHANNEL": self.db_channel,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        if not self.admins:
            raise ValueError("ADMINS must contain at least one Telegram user ID")
        if self.auto_delete_seconds < 0:
            raise ValueError("AUTO_DEL cannot be negative")
        if self.free_files < 0:
            raise ValueError("FREE_FILES cannot be negative")
        if self.subscription_stars <= 0:
            raise ValueError("SUBSCRIPTION_STARS must be greater than zero")
        if self.subscription_days <= 0:
            raise ValueError("SUBSCRIPTION_DAYS must be greater than zero")
