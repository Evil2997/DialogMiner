from pydantic import BaseModel, Field


class ChatInfo(BaseModel):
    id: int
    title: str
    username: str | None = None
    entity_type: str
    slug: str


class ArchiveMessage(BaseModel):
    id: int
    date_utc: str
    author: str
    text: str
    sender_id: int | None = None
    reply_to_msg_id: int | None = None
    forwarded_from: str | None = None
    has_media: bool = False
    is_service: bool = False


class RawArchive(BaseModel):
    chat: ChatInfo
    exported_at_utc: str
    total_messages: int
    messages: list[ArchiveMessage] = Field(default_factory=list)


class ChunkInfo(BaseModel):
    file_name: str
    start_month: str
    end_month: str
    part_index: int | None = None
    part_total: int | None = None
    message_count: int
    char_count: int
    first_message_date_utc: str
    last_message_date_utc: str


class Summary(BaseModel):
    chat: ChatInfo
    exported_at_utc: str
    total_messages: int
    first_message_date_utc: str | None = None
    last_message_date_utc: str | None = None
    authors_count: int
    text_messages: int
    service_messages: int
    media_messages: int
    forwarded_messages: int
    chunks_count: int
    chunks: list[ChunkInfo] = Field(default_factory=list)


class ChunkDraft(BaseModel):
    start_month: str
    end_month: str
    message_count: int
    char_count: int
    first_message_date_utc: str
    last_message_date_utc: str
    text: str
    file_name: str | None = None
    part_index: int | None = None
    part_total: int | None = None