import logging
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymysql.err import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.chats import router as chats_router
from backend.api.chat_pipeline import ChatPipeline
from backend.api.output_guard_adapter import check_output
from backend.api.auth import router as auth_router
from backend.api.errors import ApiError
from backend.api.saves import router as saves_router

logger = logging.getLogger(__name__)
DEFAULT_ORIGINS = [
    'https://kcg020529.github.io',
    'http://127.0.0.1:8010',
    'http://localhost:8010',
]
configured_origins = os.getenv('KERVION_ALLOWED_ORIGINS')
ALLOWED_ORIGINS = (
    [origin.strip() for origin in configured_origins.split(',') if origin.strip()]
    if configured_origins is not None else DEFAULT_ORIGINS
)

app = FastAPI()
app.state.chat_pipeline = ChatPipeline(output_guard=check_output)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT'],
    allow_headers=['Content-Type'],
)


def _error(status: int, code: str, message: str):
    request_id = f'req_{secrets.token_hex(4)}'
    return JSONResponse(
        status_code=status,
        content={'error': {'code': code, 'message': message, 'request_id': request_id}},
    )


@app.middleware('http')
async def check_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method in ('POST', 'PUT') and origin and origin not in ALLOWED_ORIGINS:
        return _error(403, 'ACCESS_DENIED', '현재 권한으로는 요청할 수 없습니다.')
    return await call_next(request)


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError):
    return _error(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    too_long_memo = any(
        error.get('type') == 'string_too_long' and error.get('loc', ())[-1:] == ('memo',)
        for error in exc.errors()
    )
    message = '메모는 5000자까지 쓸 수 있습니다.' if too_long_memo else '입력값을 확인해 주세요.'
    return _error(422, 'VALIDATION_ERROR', message)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return _error(404, 'NOT_FOUND', '요청한 항목을 찾을 수 없습니다.')
    return _error(exc.status_code, 'INVALID_REQUEST', '요청 내용을 확인해 주세요.')


async def handle_database_error(request: Request, exc: Exception):
    return _error(503, 'SERVICE_UNAVAILABLE', '잠시 후 다시 시도해 주세요.')


app.add_exception_handler(OperationalError, handle_database_error)
app.add_exception_handler(InterfaceError, handle_database_error)


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    logger.exception('Unhandled API error')
    return _error(500, 'INTERNAL_ERROR', '요청을 처리할 수 없습니다.')


app.include_router(saves_router, prefix='/api/v1')
app.include_router(chats_router, prefix='/api/v1')
app.include_router(auth_router, prefix='/api/v1')
