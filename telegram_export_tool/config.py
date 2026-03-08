from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    api_id: int
    api_hash: str
    phone: str | None = None
    session_name: str = Field(default="telegram_export_session")
    output_dir: Path = Field(default=Path("output"))


def load_settings() -> Settings:
    load_dotenv()

    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    phone = os.getenv("TG_PHONE")
    session_name = os.getenv("TG_SESSION", "telegram_export_session")
    output_dir = os.getenv("TG_OUTPUT_DIR", "output")

    if not api_id or not api_hash:
        raise RuntimeError("TG_API_ID and TG_API_HASH must be set in .env")

    return Settings(
        api_id=int(api_id),
        api_hash=api_hash,
        phone=phone,
        session_name=session_name,
        output_dir=Path(output_dir),
    )
