import enum
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db import Base

class Role(str, enum.Enum):
    teacher = "teacher"
    student = "student"

class CheckinStatus(str, enum.Enum):
    on_time = "on_time"
    late = "late"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str] = mapped_column(String(16), index=True)
    password_hash: Mapped[str] = mapped_column(Text)

    created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)

    teacher: Mapped["User"] = relationship("User")
    sessions: Mapped[list["AttendanceSession"]] = relationship("AttendanceSession", back_populates="course")

    created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)

    session_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    started_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ends_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), index=True)

    duration_min: Mapped[int] = mapped_column(Integer)
    late_after_min: Mapped[int] = mapped_column(Integer)

    is_closed: Mapped[bool] = mapped_column(Boolean, server_default="false")

    current_key: Mapped[str] = mapped_column(String(64), index=True)
    key_expires_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True))

    course: Mapped["Course"] = relationship("Course", back_populates="sessions")
    checkins: Mapped[list["CheckIn"]] = relationship("CheckIn", back_populates="session")

class CheckIn(Base):
    __tablename__ = "checkins"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_checkin_student_once"),
        UniqueConstraint("session_id", "device_id", name="uq_checkin_one_student_per_device"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("attendance_sessions.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    device_id: Mapped[str] = mapped_column(String(64), index=True)
    checked_in_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(16), index=True)

    session: Mapped["AttendanceSession"] = relationship("AttendanceSession", back_populates="checkins")
    student: Mapped["User"] = relationship("User")
