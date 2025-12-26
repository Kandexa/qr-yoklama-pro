from datetime import datetime, timedelta, timezone
import secrets
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import User, Course, AttendanceSession, CheckIn, Role, CheckinStatus

def _utcnow():
    return datetime.now(timezone.utc)

def new_session_code() -> str:
    return secrets.token_hex(4)  # 8 chars

def new_dynamic_key() -> str:
    return secrets.token_urlsafe(24)

async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    res = await db.execute(select(User).where(User.username == username))
    return res.scalar_one_or_none()

async def get_course(db: AsyncSession, course_id: int) -> Course | None:
    res = await db.execute(select(Course).where(Course.id == course_id).options(selectinload(Course.teacher)))
    return res.scalar_one_or_none()

async def list_teacher_courses(db: AsyncSession, teacher_id: int) -> list[Course]:
    res = await db.execute(select(Course).where(Course.teacher_id == teacher_id).order_by(Course.id.desc()))
    return list(res.scalars().all())

async def list_course_sessions(db: AsyncSession, course_id: int) -> list[AttendanceSession]:
    res = await db.execute(select(AttendanceSession).where(AttendanceSession.course_id == course_id).order_by(AttendanceSession.started_at_utc.desc()))
    return list(res.scalars().all())

async def get_session_by_code(db: AsyncSession, session_code: str) -> AttendanceSession | None:
    res = await db.execute(select(AttendanceSession).where(AttendanceSession.session_code == session_code).options(selectinload(AttendanceSession.course)))
    return res.scalar_one_or_none()

async def start_session(db: AsyncSession, course_id: int, duration_min: int, late_after_min: int, dynamic_key_ttl_sec: int) -> AttendanceSession:
    code = new_session_code()
    now = _utcnow()
    ends = now + timedelta(minutes=duration_min)
    key = new_dynamic_key()
    key_exp = now + timedelta(seconds=dynamic_key_ttl_sec)
    sess = AttendanceSession(
        course_id=course_id,
        session_code=code,
        duration_min=duration_min,
        late_after_min=late_after_min,
        ends_at_utc=ends,
        current_key=key,
        key_expires_at_utc=key_exp,
        is_closed=False,
    )
    db.add(sess)
    await db.commit()
    await db.refresh(sess)
    return sess

async def rotate_key_if_needed(db: AsyncSession, session_id: int, dynamic_key_ttl_sec: int) -> AttendanceSession | None:
    # called periodically; keeps key fresh while session active
    now = _utcnow()
    res = await db.execute(select(AttendanceSession).where(AttendanceSession.id == session_id))
    sess = res.scalar_one_or_none()
    if not sess:
        return None
    if sess.is_closed or now >= sess.ends_at_utc:
        # auto close
        await db.execute(update(AttendanceSession).where(AttendanceSession.id==session_id).values(is_closed=True))
        await db.commit()
        return sess
    if now >= sess.key_expires_at_utc:
        new_key = new_dynamic_key()
        new_exp = now + timedelta(seconds=dynamic_key_ttl_sec)
        await db.execute(update(AttendanceSession).where(AttendanceSession.id==session_id).values(current_key=new_key, key_expires_at_utc=new_exp))
        await db.commit()
        await db.refresh(sess)
    return sess

async def close_session(db: AsyncSession, session_id: int) -> None:
    await db.execute(update(AttendanceSession).where(AttendanceSession.id==session_id).values(is_closed=True))
    await db.commit()

async def create_checkin(db: AsyncSession, sess: AttendanceSession, student: User, device_id: str) -> CheckIn:
    now = _utcnow()
    late_cutoff = sess.started_at_utc + timedelta(minutes=sess.late_after_min)
    status = CheckinStatus.late.value if now > late_cutoff else CheckinStatus.on_time.value
    ci = CheckIn(session_id=sess.id, student_id=student.id, device_id=device_id, status=status)
    db.add(ci)
    await db.commit()
    await db.refresh(ci)
    return ci

async def session_checkins(db: AsyncSession, session_id: int) -> list[CheckIn]:
    res = await db.execute(
        select(CheckIn)
        .where(CheckIn.session_id == session_id)
        .options(selectinload(CheckIn.student))
        .order_by(CheckIn.checked_in_at_utc.asc())
    )
    return list(res.scalars().all())

async def stats_for_course(db: AsyncSession, course_id: int):
    # coarse stats; per-student counts computed in python (OK for small/medium classes)
    sessions = await list_course_sessions(db, course_id)
    out = []
    for s in sessions:
        cis = await session_checkins(db, s.id)
        out.append((s, cis))
    return out
