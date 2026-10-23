"""First FastAPI slice for J03: account sessions and the current user's Save list."""

from datetime import datetime
import os
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
import pymysql

from backend.common.database import transaction
from backend.common.security import (
    SESSION_TTL,
    hash_password,
    new_session,
    session_hash,
    verify_password,
)


API_PREFIX = "/api/v1"
COOKIE_NAME = "kervion_session"
ROLES = {"prof", "grad", "std"}
ALLOWED_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv(
        "KERVION_ALLOWED_ORIGINS",
        "http://127.0.0.1:8010,http://localhost:8010,https://kcg020529.github.io",
    ).split(",")
    if origin.strip()
)
COOKIE_SECURE = os.getenv("KERVION_COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("KERVION_COOKIE_SAMESITE", "lax").lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise ValueError("KERVION_COOKIE_SAMESITE must be lax, strict, or none")
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise ValueError("SameSite=None requires KERVION_COOKIE_SECURE=true")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


class Signup(BaseModel):
    username: str
    password: str
    role: str


class Login(BaseModel):
    username: str
    password: str


app = FastAPI(title="Kervion Backend")


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", uuid.uuid4().hex),
            }
        },
    )


@app.middleware("http")
async def request_boundary(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin not in ALLOWED_ORIGINS:
            return error_response(request, 403, "ACCESS_DENIED", "허용되지 않은 요청 출처입니다.")
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(ApiError)
async def api_error(request: Request, error: ApiError):
    return error_response(request, error.status, error.code, error.message)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, _error: RequestValidationError):
    return error_response(request, 422, "VALIDATION_ERROR", "입력값을 확인해 주세요.")


@app.exception_handler(pymysql.MySQLError)
async def database_error(request: Request, _error: pymysql.MySQLError):
    return error_response(
        request, 503, "SERVICE_UNAVAILABLE", "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
    )


def normalized_username(username: str) -> str:
    username = username.strip()
    if not 1 <= len(username) <= 50:
        raise ApiError(422, "VALIDATION_ERROR", "아이디는 1~50자로 입력해 주세요.")
    return username


def validate_password(password: str) -> None:
    byte_length = len(password.encode("utf-8"))
    if not 8 <= byte_length <= 128:
        raise ApiError(422, "VALIDATION_ERROR", "비밀번호는 UTF-8 기준 8~128바이트로 입력해 주세요.")


def account(cursor, user_id: int, username: str) -> dict:
    cursor.execute(
        "SELECT role FROM user_roles WHERE user_id = %s ORDER BY role", (user_id,)
    )
    return {
        "user_id": user_id,
        "username": username,
        "roles": [row["role"] for row in cursor.fetchall()],
    }


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=int(SESSION_TTL.total_seconds()),
        path=API_PREFIX,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )


def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise ApiError(401, "AUTH_REQUIRED", "로그인이 필요합니다.")
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.user_id, u.username
                FROM auth_sessions AS s
                JOIN users AS u ON u.user_id = s.user_id
                WHERE s.session_hash = %s AND s.expires_at > UTC_TIMESTAMP()
                """,
                (session_hash(token),),
            )
            user = cursor.fetchone()
            if not user:
                raise ApiError(401, "AUTH_REQUIRED", "접속이 만료되었습니다. 다시 로그인해 주세요.")
            return account(cursor, user["user_id"], user["username"])


@app.post(f"{API_PREFIX}/auth/signup", status_code=201)
def signup(payload: Signup):
    username = normalized_username(payload.username)
    validate_password(payload.password)
    if payload.role not in ROLES:
        raise ApiError(422, "VALIDATION_ERROR", "역할을 다시 선택해 주세요.")

    password_hash = hash_password(payload.password)
    token, token_hash, expires_at = new_session()
    try:
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                    (username, password_hash),
                )
                user_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO user_roles (user_id, role) VALUES (%s, %s)",
                    (user_id, payload.role),
                )
                cursor.execute(
                    "INSERT INTO auth_sessions (session_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                    (token_hash, user_id, expires_at),
                )
    except pymysql.IntegrityError as error:
        if error.args and error.args[0] == 1062:
            raise ApiError(409, "STATE_CONFLICT", "이미 있는 아이디입니다.") from error
        raise

    response = JSONResponse(
        status_code=201,
        content={"user_id": user_id, "username": username, "roles": [payload.role]},
    )
    set_session_cookie(response, token)
    return response


@app.post(f"{API_PREFIX}/auth/login")
def login(payload: Login):
    username = normalized_username(payload.username)
    if not payload.password:
        raise ApiError(422, "VALIDATION_ERROR", "비밀번호를 입력해 주세요.")

    with transaction() as connection:
        with connection.cursor() as cursor:
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
            result = account(cursor, user["user_id"], user["username"])

    response = JSONResponse(content=result)
    set_session_cookie(response, token)
    return response


@app.get(f"{API_PREFIX}/auth/me")
def me(user: dict = Depends(current_user)):
    return user


@app.post(f"{API_PREFIX}/auth/logout", status_code=204)
def logout(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM auth_sessions WHERE session_hash = %s",
                    (session_hash(token),),
                )
    response = Response(status_code=204)
    response.delete_cookie(
        key=COOKIE_NAME,
        path=API_PREFIX,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
    return response


@app.get(f"{API_PREFIX}/saves")
def list_saves(user: dict = Depends(current_user)):
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT save_id, slot_no, role, day, created_at, last_played_at
                FROM saves
                WHERE user_id = %s
                ORDER BY slot_no
                """,
                (user["user_id"],),
            )
            rows = cursor.fetchall()
    return {
        "saves": [
            {
                **row,
                "created_at": format_datetime(row["created_at"]),
                "last_played_at": format_datetime(row["last_played_at"]),
            }
            for row in rows
        ]
    }


def format_datetime(value: datetime) -> str:
    return value.isoformat(timespec="seconds")
