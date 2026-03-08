from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TG_",
        case_sensitive=False,
    )

    api_id: int
    api_hash: str
    phone: str | None = None

    session_name: str = Field(default="telegram_export_session")

    output_dir: Path = Field(default=Path("output"))
    state_dir: Path = Field(default=Path("state"))

    def chat_output_dir(self, slug: str) -> Path:
        return self.output_dir / slug

    def selected_dialogs_path(self) -> Path:
        return self.state_dir / "selected_dialogs.json"

    def scan_cache_path(self) -> Path:
        return self.state_dir / "scanned_dialogs.json"


settings = Settings()
