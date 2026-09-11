from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
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


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    authors: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    google_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    meetings: Mapped[list["Meeting"]] = relationship(back_populates="book")
    votes: Mapped[list["Vote"]] = relationship(back_populates="book", cascade="all, delete-orphan")


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="PLANNED", nullable=False)

    book: Mapped[Book | None] = relationship(back_populates="meetings")
    votes: Mapped[list["Vote"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    rsvps: Mapped[list["RSVP"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")


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
