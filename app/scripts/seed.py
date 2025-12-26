import asyncio
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User, Course, Role
from app.security import hash_password

async def main():
    async with SessionLocal() as db:
        # Teacher
        t = (await db.execute(select(User).where(User.username=="teacher1"))).scalar_one_or_none()
        if not t:
            t = User(username="teacher1", full_name="Teacher One", role=Role.teacher.value, password_hash=hash_password("Teacher123!"))
            db.add(t)
            await db.commit()
            await db.refresh(t)

        # Students
        for uname, fname in [("student1","Student One"),("student2","Student Two")]:
            s = (await db.execute(select(User).where(User.username==uname))).scalar_one_or_none()
            if not s:
                db.add(User(username=uname, full_name=fname, role=Role.student.value, password_hash=hash_password("Student123!")))
        await db.commit()

        # Course
        c = (await db.execute(select(Course).where(Course.teacher_id==t.id).where(Course.name=="Matematik"))).scalar_one_or_none()
        if not c:
            db.add(Course(teacher_id=t.id, name="Matematik"))
            await db.commit()

    print("Seed tamam ✅")

if __name__ == "__main__":
    asyncio.run(main())
