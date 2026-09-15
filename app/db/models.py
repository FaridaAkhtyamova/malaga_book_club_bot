from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="MEMBER", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    votes: Mapped[list["Vote"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    rsvps: Mapped[list["RSVP"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    suggestions: Mapped[list["Suggestion"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    authors: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    google_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    meetings: Mapped[list["Meeting"]] = relationship(back_populates="book")
    votes: Mapped[list["Vote"]] = relationship(back_populates="book", cascade="all, delete-orphan")
    suggestions: Mapped[list["Suggestion"]] = relationship(back_populates="book")
    vote_wins: Mapped[list["SuggestionCycle"]] = relationship(
        back_populates="winner",
        foreign_keys="SuggestionCycle.winner_book_id",
    )


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="PLANNED", nullable=False)

    book: Mapped[Book | None] = relationship(back_populates="meetings")
    votes: Mapped[list["Vote"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    rsvps: Mapped[list["RSVP"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)

    meeting: Mapped[Meeting] = relationship(back_populates="votes")
    user: Mapped[User] = relationship(back_populates="votes")
    book: Mapped[Book] = relationship(back_populates="votes")


class RSVP(Base):
    __tablename__ = "rsvps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    meeting: Mapped[Meeting] = relationship(back_populates="rsvps")
    user: Mapped[User] = relationship(back_populates="rsvps")


class ClubSettings(Base):
    __tablename__ = "club_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    suggest_topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    suggest_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vote_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    announce_hour: Mapped[int] = mapped_column(Integer, default=10, nullable=False)


class SuggestionCycle(Base):
    __tablename__ = "suggestion_cycles"
    __table_args__ = (
        UniqueConstraint("target_year", "target_month", name="uq_cycle_target_month"),
    )

    STATUS_SUGGESTING = "SUGGESTING"
    STATUS_VOTING = "VOTING"
    STATUS_CLOSED = "CLOSED"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target_year: Mapped[int] = mapped_column(Integer, nullable=False)
    target_month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default=STATUS_SUGGESTING, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    winner_book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)

    suggestions: Mapped[list["Suggestion"]] = relationship(
        back_populates="cycle", cascade="all, delete-orphan"
    )
    vote_polls: Mapped[list["VotePoll"]] = relationship(
        back_populates="cycle", cascade="all, delete-orphan"
    )
    winner: Mapped[Book | None] = relationship(
        back_populates="vote_wins",
        foreign_keys=[winner_book_id],
    )


class VotePoll(Base):
    __tablename__ = "vote_polls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("suggestion_cycles.id"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_poll_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    option_book_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    cycle: Mapped[SuggestionCycle] = relationship(back_populates="vote_polls")


class Suggestion(Base):
    __tablename__ = "suggestions"
    __table_args__ = (UniqueConstraint("cycle_id", "book_id", name="uq_suggestion_cycle_book"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("suggestion_cycles.id"), nullable=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    cycle: Mapped[SuggestionCycle] = relationship(back_populates="suggestions")
    book: Mapped[Book] = relationship(back_populates="suggestions")
    user: Mapped[User] = relationship(back_populates="suggestions")
