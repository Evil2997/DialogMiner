from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from telegram_export_tool.constants import DEFAULT_SESSION_NAME
from telegram_export_tool.paths import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATE_DIR,
    build_chat_output_dir,
    build_scanned_dialogs_path,
    build_selected_dialogs_path,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TG_",
        case_sensitive=False,
    )

    api_id: int
    api_hash: str
    phone: str | None = None

    session_name: str = Field(default=DEFAULT_SESSION_NAME)

    output_dir: Path = Field(default=DEFAULT_OUTPUT_DIR)
    state_dir: Path = Field(default=DEFAULT_STATE_DIR)

    def chat_output_dir(self, slug: str) -> Path:
        return build_chat_output_dir(self.output_dir, slug)

    def selected_dialogs_path(self) -> Path:
        return build_selected_dialogs_path(self.state_dir)

    def scanned_dialogs_path(self) -> Path:
        return build_scanned_dialogs_path(self.state_dir)


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    return Settings()


settings = load_settings()
