from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Clan(Base):
    __tablename__ = "clans"

    id: Mapped[int] = mapped_column(primary_key=True)
    wg_clan_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    tag: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(128))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(clan_id IS NULL) = (clan_role IS NULL)",
            name="ck_users_clan_id_role_consistent",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wg_account_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(64))
    clan_id: Mapped[int | None] = mapped_column(ForeignKey("clans.id"), nullable=True)
    clan_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    clan: Mapped["Clan | None"] = relationship()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AttendanceCode(Base):
    __tablename__ = "attendance_codes"
    __table_args__ = (
        UniqueConstraint(
            "clan_id", "attendance_date", name="uq_attendance_codes_clan_date"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    clan_id: Mapped[int] = mapped_column(ForeignKey("clans.id"), index=True)
    code: Mapped[str] = mapped_column(String(6))
    attendance_date: Mapped[date] = mapped_column(Date)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint(
            "clan_id", "user_id", "attendance_date", name="uq_attendance_clan_user_date"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    clan_id: Mapped[int] = mapped_column(ForeignKey("clans.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    attendance_date: Mapped[date] = mapped_column(Date)
    # self check-in: code_id set, overridden_by_id null.
    # admin override: overridden_by_id set, code_id null.
    code_id: Mapped[int | None] = mapped_column(
        ForeignKey("attendance_codes.id"), nullable=True
    )
    overridden_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
