from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
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
