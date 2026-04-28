"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "dlp-archive"
    debug: bool = False
    allowed_origins: list[str] = ["*"]
    credentials_path: str = "/config/credentials.json"
    drive_folder: str = "dlp-archive"
    storage_backend: str = "gdrive"
    local_storage_path: str = "./archive"
    redoc_enabled: bool = False
    yt_cookies_path: str | None = None
    ytdl_proxy: str | None = None


settings = Settings()
