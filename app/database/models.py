from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
	return datetime.now(timezone.utc)


class Base(DeclarativeBase):
	pass


class User(Base):
	__tablename__ = "users"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
	username: Mapped[str | None] = mapped_column(String(64), nullable=True)
	first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
	is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
	custom_daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

	readings: Mapped[list["Reading"]] = relationship(
		back_populates="user",
		cascade="all, delete-orphan",
	)
	daily_cards: Mapped[list["DailyCardLog"]] = relationship(
		back_populates="user",
		cascade="all, delete-orphan",
	)


class DailyCardLog(Base):
	# Фиксация одной «Карты дня» на календарную дату по МСК
	__tablename__ = "daily_cards"
	__table_args__ = (
		UniqueConstraint("user_id", "msk_date", name="uq_user_daily_card_date"),
	)

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
	msk_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
	card_id: Mapped[str] = mapped_column(String(64), nullable=False)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

	user: Mapped["User"] = relationship(back_populates="daily_cards")


class Reading(Base):
	__tablename__ = "readings"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
	question: Mapped[str] = mapped_column(Text, nullable=False)
	card_1_name: Mapped[str] = mapped_column(String(100), nullable=False)
	card_2_name: Mapped[str] = mapped_column(String(100), nullable=False)
	card_3_name: Mapped[str] = mapped_column(String(100), nullable=False)
	ai_interpretation: Mapped[str] = mapped_column(Text, nullable=False)
	followup_question: Mapped[str | None] = mapped_column(Text, nullable=True)
	followup_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
	feedback_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
	feedback_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)

	user: Mapped["User"] = relationship(back_populates="readings")
