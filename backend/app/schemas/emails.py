from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str
    text_content: str | None


class EmailSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str | None
    sender: str
    subject: str
    received_at: datetime
    status: str
    order_id: int | None
    classification: dict[str, Any] | None
    review_count: int = 0


class EmailDetail(EmailSummary):
    body: str
    attachments: list[AttachmentOut]
    extraction: dict[str, Any] | None
    analysis_error: str | None
    # Set when the response is a stored result instead of a fresh run.
    notice: str | None = None
