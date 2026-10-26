"""Authenticated user lookup shared by Save and chat routes."""

from fastapi import Depends, Request
from pymysql.connections import Connection

from backend.api.db import get_db
from backend.api.errors import ApiError
from backend.common.security import session_hash


COOKIE_NAME = "kervion_session"


def current_user_id(request: Request, conn: Connection = Depends(get_db)) -> int:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise ApiError(401, "AUTH_REQUIRED", "로그인이 필요합니다.")
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT user_id FROM auth_sessions "
            "WHERE session_hash = %s AND expires_at > UTC_TIMESTAMP()",
            (session_hash(token),),
        )
        row = cursor.fetchone()
        if not row:
            raise ApiError(401, "AUTH_REQUIRED", "접속이 만료되었습니다. 다시 로그인해 주세요.")
        return int(row["user_id"])
