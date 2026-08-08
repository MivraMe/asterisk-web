from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import UserOut
from app.templating import templates
from app.security import (
    check_login_rate_limit,
    create_session_token,
    record_login_attempt,
    verify_password,
)

router = APIRouter()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: AsyncSession = Depends(get_db),
):
    ip = _client_ip(request)
    redirect_to = next if next.startswith("/") else "/"

    def fail(status_code: int, message: str):
        if _wants_json(request):
            raise HTTPException(status_code=status_code, detail=message)
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {"error": message, "next": redirect_to, "username": username},
            status_code=status_code,
        )

    if not check_login_rate_limit(ip):
        return fail(429, "Too many login attempts — try again in a minute.")

    record_login_attempt(ip)

    user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return fail(401, "Invalid username or password.")

    token = create_session_token(user.id)

    if _wants_json(request):
        resp: Response = JSONResponse({"status": "ok"})
    else:
        resp = RedirectResponse(url=redirect_to, status_code=303)

    resp.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return resp


@router.post("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(settings.session_cookie_name)
    return resp


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
