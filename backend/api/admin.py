"""Website administrator check and the audit dashboard shell."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from pymysql.connections import Connection

from backend.api.current_user import current_user_id
from backend.api.db import get_db
from backend.api.errors import ApiError


router = APIRouter(prefix="/admin")
PAGE = Path(__file__).with_name("admin_audit.html")


def current_site_admin_id(
    user_id: int = Depends(current_user_id),
    conn: Connection = Depends(get_db, scope="function"),
) -> int:
    with conn.cursor() as cursor:
        cursor.execute("SELECT user_id FROM site_admins WHERE user_id = %s", (user_id,))
        if cursor.fetchone() is None:
            raise ApiError(403, "ACCESS_DENIED", "관리자만 볼 수 있습니다.")
    return user_id


@router.get("/check", include_in_schema=False)
def check_admin(user_id: int = Depends(current_site_admin_id)):
    return Response(
        status_code=204,
        headers={"X-Kervion-Admin-Id": f"kervion-{user_id}", "Cache-Control": "no-store"},
    )


@router.get("/audit", response_class=HTMLResponse, include_in_schema=False)
def audit_page(user_id: int = Depends(current_site_admin_id)):
    return HTMLResponse(
        PAGE.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store", "Content-Security-Policy": "frame-src 'self'"},
    )
