from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from app.config import settings
from app.security import read_session_token

PUBLIC_PATHS = {"/login", "/health"}
PUBLIC_PREFIXES = ("/static/", "/api/auth/login")


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if _is_public(path):
            return await call_next(request)

        token = request.cookies.get(settings.session_cookie_name)
        user_id = read_session_token(token) if token else None

        if user_id is None:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            return RedirectResponse(url=f"/login?next={path}", status_code=303)

        request.state.user_id = user_id
        return await call_next(request)
