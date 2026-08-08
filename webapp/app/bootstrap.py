import logging
import secrets

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User
from app.security import hash_password

logger = logging.getLogger(__name__)


async def ensure_admin_user(db: AsyncSession) -> None:
    """No data migration happens for this rebuild (spec section 8) — but a
    single admin account has to exist for anyone to log in at all. Create
    one from ADMIN_USERNAME/ADMIN_PASSWORD the first time the users table is
    empty; a random password is generated and logged if none was set."""
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    if count > 0:
        return

    password = settings.admin_password or secrets.token_urlsafe(16)
    user = User(username=settings.admin_username, password_hash=hash_password(password))
    db.add(user)
    await db.commit()

    if settings.admin_password:
        logger.info("Bootstrapped admin user %r from ADMIN_USERNAME/ADMIN_PASSWORD", settings.admin_username)
    else:
        logger.warning(
            "No ADMIN_PASSWORD set — bootstrapped admin user %r with a random password: %s "
            "(change it after logging in; this is only logged once)",
            settings.admin_username,
            password,
        )
