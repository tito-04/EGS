from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import get_db
from app.models import RoleEnum, User

router = APIRouter(prefix="/internal/kpi", tags=["kpi"])


def _verify_internal_service_key(
    x_internal_service_key: str | None = Header(default=None, alias="X-Internal-Service-Key"),
) -> None:
    if x_internal_service_key != settings.INTERNAL_SERVICE_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service key",
        )


def _role_key(role: RoleEnum | str | None) -> str:
    if isinstance(role, RoleEnum):
        return role.value
    if role is None:
        return "unknown"
    return str(role).lower()


@router.get("/snapshot", summary="Auth KPI snapshot")
async def get_kpi_snapshot(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_internal_service_key),
):
    grouped = await db.execute(
        select(User.role, User.is_active, func.count(User.id))
        .group_by(User.role, User.is_active)
    )

    by_role = {role.value: 0 for role in RoleEnum}
    total = 0
    active = 0

    for role, is_active, count in grouped.all():
        count = int(count or 0)
        role_name = _role_key(role)
        by_role[role_name] = by_role.get(role_name, 0) + count
        total += count
        if is_active:
            active += count

    return {
        "enabled": True,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "users": {
            "total": total,
            "active": active,
            "inactive": max(total - active, 0),
            "by_role": by_role,
        },
    }
