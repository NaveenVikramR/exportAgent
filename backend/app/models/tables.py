from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (UniqueConstraint("external_id", name="uq_emails_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # eval/seed case id, so seeding is idempotent
    external_id: Mapped[str | None] = mapped_column(String(50))
    sender: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # seed | paste | upload
    source: Mapped[str] = mapped_column(String(20), default="seed")
    # new | processing | analysed | needs_review | failed
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    classification: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    # {"fields": POExtraction, "review": [ReviewFlag]}; null when the email carries no PO data
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    analysis_error: Mapped[str | None] = mapped_column(Text)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    attachments: Mapped[list["EmailAttachment"]] = relationship(
        back_populates="email", cascade="all, delete-orphan"
    )
    order: Mapped["Order | None"] = relationship()


class EmailAttachment(Base):
    __tablename__ = "email_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    text_content: Mapped[str | None] = mapped_column(Text)

    email: Mapped[Email] = relationship(back_populates="attachments")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("buyer", "po_number", name="uq_orders_buyer_po"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer: Mapped[str] = mapped_column(String(200), index=True)
    po_number: Mapped[str] = mapped_column(String(100), index=True)
    style: Mapped[str | None] = mapped_column(String(200))
    # open | at_risk | confirmed | shipped | cancelled
    status: Mapped[str] = mapped_column(String(20), default="open")
    # factory/country profile the order was processed under
    profile: Mapped[str] = mapped_column(String(50))
    current_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    versions: Mapped[list["POVersion"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="POVersion.version"
    )


class POVersion(Base):
    __tablename__ = "po_versions"
    __table_args__ = (UniqueConstraint("order_id", "version", name="uq_po_versions_order_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    version: Mapped[int]
    email_id: Mapped[int | None] = mapped_column(ForeignKey("emails.id"))
    # document: values from a PO or order email; thread_reference: earlier values quoted in a reply thread
    basis: Mapped[str] = mapped_column(String(30), default="document", server_default="document")
    # PO snapshot, per-field confidence, and the diff against the previous version
    data: Mapped[dict[str, Any]] = mapped_column(JSON(none_as_null=True))
    confidence: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    changes: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    order: Mapped[Order] = relationship(back_populates="versions")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int | None] = mapped_column(ForeignKey("emails.id"), index=True)
    # running | completed | needs_review | failed
    status: Mapped[str] = mapped_column(String(20), default="running")
    rounds: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentStep.seq"
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    seq: Mapped[int]
    # llm | tool
    kind: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100))
    input: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[AgentRun] = relationship(back_populates="steps")


class LLMCall(Base):
    """One row per Token Factory call, written by the router."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(40), index=True)
    tier: Mapped[str] = mapped_column(String(10))
    model: Mapped[str] = mapped_column(String(200), index=True)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    latency_ms: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0"))
    # live | cache | mock. Only live calls cost money.
    source: Mapped[str] = mapped_column(String(10), default="live", server_default="live")
    success: Mapped[bool] = mapped_column(default=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class LLMCache(Base):
    """Live responses keyed by request hash, so re-runs do not re-spend credits."""

    __tablename__ = "llm_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(200))
    response: Mapped[dict[str, Any]] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Draft(Base):
    """A drafted message waiting in the approval queue. Nothing is sent automatically."""

    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    # buyer_reply | internal_note
    kind: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    edited_body: Mapped[str | None] = mapped_column(Text)
    # pending | approved | rejected | sent
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    po_version: Mapped[int]
    # commercial_invoice | packing_list
    kind: Mapped[str] = mapped_column(String(30))
    path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
