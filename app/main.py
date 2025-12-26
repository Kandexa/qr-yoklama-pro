import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Depends, Form, Response, WebSocket, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.db import get_db, engine
from app import models
from app.security import verify_password, create_token, set_auth_cookie, clear_auth_cookie, get_current_username
from app.time_utils import fmt_local
from app.qr_utils import make_qr_png
from app.ws import manager
from app import repos

app = FastAPI(title="QR Yoklama Pro")
templates = Jinja2Templates(directory="app/templates")

# Helpers
async def current_user(db: AsyncSession, request: Request):
    uname = get_current_username(request)
    if not uname:
        return None
    return await repos.get_user_by_username(db, uname)

def ensure_device_id(resp: Response, request: Request) -> str:
    device_id = request.cookies.get("device_id")
    if not device_id:
        device_id = repos.new_dynamic_key()
        resp.set_cookie("device_id", device_id, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=3600*24*365)
    return device_id

@app.on_event("startup")
async def startup():
    # optional: auto-run migrations (useful on Render first deploy)
    if settings.migrate_on_start:
        try:
            from alembic import command
            from alembic.config import Config
            cfg = Config("alembic.ini")
            command.upgrade(cfg, "head")
        except Exception as e:
            # don't crash hard; surface in logs
            print("MIGRATION FAILED:", repr(e))

# Public
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if not me:
        return RedirectResponse("/login", status_code=302)
    if me.role == models.Role.teacher.value:
        return RedirectResponse("/teacher", status_code=302)
    return HTMLResponse("<h1>Öğrenci hesabı ile giriş yaptın.</h1><p>Yoklama için QR okut.</p>")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str | None = None, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if me:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "title": "Giriş", "me": None, "flash": None, "next": next or "/"})

@app.post("/login")
async def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    u = await repos.get_user_by_username(db, username)
    if not u or not verify_password(password, u.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "title": "Giriş", "me": None, "flash": "Kullanıcı adı veya şifre hatalı.", "next": next or "/"}, status_code=400)
    token = create_token(u.username)
    resp = RedirectResponse(next or "/", status_code=302)
    set_auth_cookie(resp, token)
    ensure_device_id(resp, request)
    return resp

@app.get("/logout")
async def logout(resp: Response):
    r = RedirectResponse("/login", status_code=302)
    clear_auth_cookie(r)
    return r

# Teacher
@app.get("/teacher", response_class=HTMLResponse)
async def teacher_home(request: Request, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if not me or me.role != models.Role.teacher.value:
        return RedirectResponse("/login", status_code=302)
    courses = await repos.list_teacher_courses(db, me.id)
    return templates.TemplateResponse("teacher_home.html", {"request": request, "me": me, "courses": courses, "flash": None})

@app.get("/teacher/course/{course_id}", response_class=HTMLResponse)
async def teacher_course(course_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if not me or me.role != models.Role.teacher.value:
        return RedirectResponse("/login", status_code=302)
    course = await repos.get_course(db, course_id)
    if not course or course.teacher_id != me.id:
        raise HTTPException(404)
    sessions = await repos.list_course_sessions(db, course_id)
    return templates.TemplateResponse(
        "teacher_course.html",
        {
            "request": request,
            "me": me,
            "course": course,
            "sessions": sessions,
            "fmt_local": fmt_local,
            "default_late_after_min": settings.late_after_min,
            "flash": None,
        },
    )

@app.post("/teacher/course/{course_id}/start")
async def teacher_start(course_id: int, request: Request, duration_min: int = Form(...), late_after_min: int = Form(...), db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if not me or me.role != models.Role.teacher.value:
        return RedirectResponse("/login", status_code=302)
    course = await repos.get_course(db, course_id)
    if not course or course.teacher_id != me.id:
        raise HTTPException(404)
    sess = await repos.start_session(db, course_id, duration_min, late_after_min, settings.dynamic_key_ttl_sec)
    # Background key rotation loop for this session
    asyncio.create_task(_key_rotation_loop(sess.id))
    return RedirectResponse(f"/teacher/session/{sess.session_code}", status_code=302)

async def _key_rotation_loop(session_id: int):
    from app.db import SessionLocal
    while True:
        async with SessionLocal() as db:
            sess = await repos.rotate_key_if_needed(db, session_id, settings.dynamic_key_ttl_sec)
            if not sess or sess.is_closed:
                return
        await asyncio.sleep(1)

@app.get("/teacher/session/{session_code}", response_class=HTMLResponse)
async def teacher_session(session_code: str, request: Request, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if not me or me.role != models.Role.teacher.value:
        return RedirectResponse("/login", status_code=302)
    sess = await repos.get_session_by_code(db, session_code)
    if not sess:
        raise HTTPException(404)
    course = await repos.get_course(db, sess.course_id)
    if not course or course.teacher_id != me.id:
        raise HTTPException(403)
    # auto-close if time passed
    await repos.rotate_key_if_needed(db, sess.id, settings.dynamic_key_ttl_sec)

    rows = await repos.session_checkins(db, sess.id)
    counts = {
        "total": len(rows),
        "on_time": sum(1 for r in rows if r.status == models.CheckinStatus.on_time.value),
        "late": sum(1 for r in rows if r.status == models.CheckinStatus.late.value),
    }
    return templates.TemplateResponse(
        "teacher_session.html",
        {
            "request": request,
            "me": me,
            "session": sess,
            "rows": rows,
            "counts": counts,
            "fmt_local": fmt_local,
            "dynamic_key_ttl_sec": settings.dynamic_key_ttl_sec,
            "flash": None,
        },
    )

@app.post("/teacher/session/{session_code}/close")
async def teacher_close(session_code: str, request: Request, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if not me or me.role != models.Role.teacher.value:
        return RedirectResponse("/login", status_code=302)
    sess = await repos.get_session_by_code(db, session_code)
    if not sess:
        raise HTTPException(404)
    course = await repos.get_course(db, sess.course_id)
    if not course or course.teacher_id != me.id:
        raise HTTPException(403)
    await repos.close_session(db, sess.id)
    return RedirectResponse(f"/teacher/session/{session_code}", status_code=302)

@app.get("/teacher/session/{session_code}/qr.png")
async def teacher_qr_png(session_code: str, request: Request, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if not me or me.role != models.Role.teacher.value:
        raise HTTPException(401)
    sess = await repos.get_session_by_code(db, session_code)
    if not sess:
        raise HTTPException(404)
    course = await repos.get_course(db, sess.course_id)
    if not course or course.teacher_id != me.id:
        raise HTTPException(403)
    await repos.rotate_key_if_needed(db, sess.id, settings.dynamic_key_ttl_sec)
    # build QR url
    url = f"{settings.app_base_url}/s/{sess.session_code}?k={sess.current_key}"
    png = make_qr_png(url)
    return Response(content=png, media_type="image/png")

@app.get("/teacher/session/{session_code}/csv")
async def teacher_csv(session_code: str, request: Request, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if not me or me.role != models.Role.teacher.value:
        raise HTTPException(401)
    sess = await repos.get_session_by_code(db, session_code)
    if not sess:
        raise HTTPException(404)
    course = await repos.get_course(db, sess.course_id)
    if not course or course.teacher_id != me.id:
        raise HTTPException(403)
    rows = await repos.session_checkins(db, sess.id)

    def gen():
        yield "time_local,username,full_name,status\n"
        for r in rows:
            yield f"{fmt_local(r.checked_in_at_utc, True)},{r.student.username},{(r.student.full_name or '').replace(',', ' ')},{r.status}\n"

    filename = f"session_{sess.session_code}.csv"
    return StreamingResponse(gen(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.get("/teacher/course/{course_id}/stats", response_class=HTMLResponse)
async def teacher_stats(course_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if not me or me.role != models.Role.teacher.value:
        return RedirectResponse("/login", status_code=302)
    course = await repos.get_course(db, course_id)
    if not course or course.teacher_id != me.id:
        raise HTTPException(404)

    items = await repos.stats_for_course(db, course_id)
    rows = []
    total_sessions = len(items)
    total_checkins = 0
    for sess, cis in items:
        late = sum(1 for c in cis if c.status == models.CheckinStatus.late.value)
        rows.append({"session": sess, "total": len(cis), "late": late})
        total_checkins += len(cis)
    avg = (total_checkins / total_sessions) if total_sessions else 0
    return templates.TemplateResponse(
        "teacher_stats.html",
        {
            "request": request,
            "me": me,
            "course": course,
            "rows": rows,
            "total_sessions": total_sessions,
            "total_checkins": total_checkins,
            "avg_per_session": f"{avg:.1f}",
            "fmt_local": fmt_local,
            "flash": None,
        },
    )

# Student scan/checkin
@app.get("/s/{session_code}", response_class=HTMLResponse)
async def student_scan(session_code: str, k: str, request: Request, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    sess = await repos.get_session_by_code(db, session_code)
    if not sess:
        raise HTTPException(404)
    # auto-close if needed and rotate key
    await repos.rotate_key_if_needed(db, sess.id, settings.dynamic_key_ttl_sec)

    # Validate dynamic key
    now = datetime.now(timezone.utc)
    if sess.is_closed or now >= sess.ends_at_utc:
        return templates.TemplateResponse("student_scan.html", {"request": request, "me": me, "session": sess, "k": k, "next_url": "/", "flash": None})
    if k != sess.current_key or now >= sess.key_expires_at_utc:
        return HTMLResponse("<h1>QR anahtarı süresi doldu. Lütfen QR'ı tekrar okut.</h1>", status_code=403)

    next_url = f"/s/{session_code}?k={k}"
    return templates.TemplateResponse("student_scan.html", {"request": request, "me": me, "session": sess, "k": k, "next_url": next_url, "flash": None})

@app.post("/s/{session_code}/checkin", response_class=HTMLResponse)
async def student_checkin(session_code: str, k: str, request: Request, db: AsyncSession = Depends(get_db)):
    me = await current_user(db, request)
    if not me or me.role != models.Role.student.value:
        return RedirectResponse(f"/login?next=/s/{session_code}?k={k}", status_code=302)

    sess = await repos.get_session_by_code(db, session_code)
    if not sess:
        raise HTTPException(404)

    await repos.rotate_key_if_needed(db, sess.id, settings.dynamic_key_ttl_sec)
    now = datetime.now(timezone.utc)

    if sess.is_closed or now >= sess.ends_at_utc:
        return HTMLResponse("<h1>Oturum kapalı.</h1>", status_code=400)
    if k != sess.current_key or now >= sess.key_expires_at_utc:
        return HTMLResponse("<h1>QR anahtarı süresi doldu. Lütfen QR'ı tekrar okut.</h1>", status_code=403)

    # device rule
    resp = Response()
    device_id = ensure_device_id(resp, request)

    # Create checkin
    try:
        ci = await repos.create_checkin(db, sess, me, device_id)
    except Exception as e:
        # likely unique constraint: already checked in or device used
        msg = "Bu oturumda zaten yoklama verdin veya bu cihaz başka öğrenci için kullanıldı."
        return HTMLResponse(f"<h1>{msg}</h1>", status_code=400)

    # broadcast
    rows = await repos.session_checkins(db, sess.id)
    counts = {
        "total": len(rows),
        "on_time": sum(1 for r in rows if r.status == models.CheckinStatus.on_time.value),
        "late": sum(1 for r in rows if r.status == models.CheckinStatus.late.value),
    }
    await manager.broadcast(
        room=sess.session_code,
        message={
            "type": "checkin",
            "student": me.full_name or me.username,
            "status": ci.status,
            "status_label": ("GEÇ" if ci.status == "late" else "ZAMANINDA"),
            "time_local": fmt_local(ci.checked_in_at_utc, True),
            "counts": counts,
        },
    )

    html = templates.TemplateResponse(
        "student_result.html",
        {"request": request, "me": me, "session": sess, "status": ci.status, "time_local": fmt_local(ci.checked_in_at_utc, True), "flash": None},
    )
    # merge device cookie into response
    for header, value in resp.raw_headers:
        html.raw_headers.append((header, value))
    return html

# WebSocket for teacher live panel
@app.websocket("/ws/session/{session_code}")
async def ws_session(ws: WebSocket, session_code: str):
    await manager.connect(session_code, ws)
    try:
        while True:
            # keep connection alive; ignore incoming
            await ws.receive_text()
    except Exception:
        pass
    finally:
        await manager.disconnect(session_code, ws)
