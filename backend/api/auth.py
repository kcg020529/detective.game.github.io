"""Account endpoints expected by J03's frontend/play/api.js."""

import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from pymysql.connections import Connection
from pymysql.err import IntegrityError

from backend.api.current_user import COOKIE_NAME, current_user_id
from backend.api.db import get_db
from backend.api.errors import ApiError
from backend.common.security import (
    SESSION_TTL,
    hash_password,
    new_session,
    session_hash,
    verify_password,
)


router = APIRouter(prefix="/auth")
ROLES = {"prof", "grad", "std"}
COOKIE_SECURE = os.getenv("KERVION_COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("KERVION_COOKIE_SAMESITE", "lax").lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise ValueError("KERVION_COOKIE_SAMESITE must be lax, strict, or none")
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise ValueError("SameSite=None requires KERVION_COOKIE_SECURE=true")


class Signup(BaseModel):
    username: str
    password: str
    role: str


class Login(BaseModel):
    username: str
    password: str


def normalized_username(username: str) -> str:
    username = username.strip()
    if not 1 <= len(username) <= 50:
        raise ApiError(422, "VALIDATION_ERROR", "아이디는 1~50자로 입력해 주세요.")
    return username


def validate_password(password: str) -> None:
    if not 8 <= len(password.encode("utf-8")) <= 128:
        raise ApiError(422, "VALIDATION_ERROR", "비밀번호는 UTF-8 기준 8~128바이트로 입력해 주세요.")


def _account(cursor, user_id: int, username: str) -> dict:
    cursor.execute("SELECT role FROM user_roles WHERE user_id = %s ORDER BY role", (user_id,))
    return {
        "user_id": user_id,
        "username": username,
        "roles": [row["role"] for row in cursor.fetchall()],
    }


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/api/v1",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )


@router.post("/signup", status_code=201)
def signup(payload: Signup, conn: Connection = Depends(get_db)):
    username = normalized_username(payload.username)
    validate_password(payload.password)
    if payload.role not in ROLES:
        raise ApiError(422, "VALIDATION_ERROR", "역할을 다시 선택해 주세요.")
    password_hash = hash_password(payload.password)
    token, token_hash, expires_at = new_session()
    with conn.cursor() as cursor:
        try:
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (username, password_hash),
            )
        except IntegrityError as error:
            if error.args and error.args[0] == 1062:
                raise ApiError(409, "STATE_CONFLICT", "이미 있는 아이디입니다.") from error
            raise
        user_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO user_roles (user_id, role) VALUES (%s, %s)",
            (user_id, payload.role),
        )
        cursor.execute(
            "INSERT INTO auth_sessions (session_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (token_hash, user_id, expires_at),
        )
    response = JSONResponse(
        status_code=201,
        content={"user_id": user_id, "username": username, "roles": [payload.role]},
    )
    _set_cookie(response, token)
    return response


@router.post("/login")
def login(payload: Login, conn: Connection = Depends(get_db)):
    username = normalized_username(payload.username)
    if not payload.password:
        raise ApiError(422, "VALIDATION_ERROR", "비밀번호를 입력해 주세요.")
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT user_id, username, password_hash FROM users WHERE username = %s",
            (username,),
        )
        user = cursor.fetchone()
        if not user or not verify_password(payload.password, user["password_hash"]):
            raise ApiError(401, "AUTH_REQUIRED", "아이디 또는 비밀번호가 맞지 않습니다.")
        token, token_hash, expires_at = new_session()
        cursor.execute(
            "INSERT INTO auth_sessions (session_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (token_hash, user["user_id"], expires_at),
        )
        result = _account(cursor, user["user_id"], user["username"])
    response = JSONResponse(content=result)
    _set_cookie(response, token)
    return response


@router.get("/me")
def me(user_id: int = Depends(current_user_id), conn: Connection = Depends(get_db)):
    with conn.cursor() as cursor:
        cursor.execute("SELECT username FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise ApiError(401, "AUTH_REQUIRED", "접속이 만료되었습니다. 다시 로그인해 주세요.")
        return _account(cursor, user_id, user["username"])


@router.post("/logout", status_code=204)
def logout(request: Request, conn: Connection = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM auth_sessions WHERE session_hash = %s",
                (session_hash(token),),
            )
    response = Response(status_code=204)
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/api/v1",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
    return response
