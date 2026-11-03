from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from fastapi.responses import Response

from backend.api.admin import router
from backend.api.auth import _set_cookie
from backend.api.current_user import current_user_id
from backend.api.db import get_db
from backend.api.errors import ApiError


class FakeCursor:
    def __init__(self, allowed):
        self.allowed = allowed
        self.params = None

    def execute(self, query, params):
        assert query == "SELECT user_id FROM site_admins WHERE user_id = %s"
        self.params = params

    def fetchone(self):
        return {"user_id": self.params[0]} if self.allowed else None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class FakeConnection:
    def __init__(self, allowed):
        self.allowed = allowed

    def cursor(self):
        return FakeCursor(self.allowed)


def client_for(user_id=None, allowed=False):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: FakeConnection(allowed)

    def user():
        if user_id is None:
            raise ApiError(401, "AUTH_REQUIRED", "로그인이 필요합니다.")
        return user_id

    app.dependency_overrides[current_user_id] = user

    @app.exception_handler(ApiError)
    def handle_error(request, error):
        return JSONResponse({"code": error.code}, status_code=error.status)

    return TestClient(app)


def test_admin_routes_reject_guest_and_regular_user():
    for client, status in ((client_for(), 401), (client_for(2), 403)):
        assert client.get("/admin/check").status_code == status
        assert client.get("/admin/audit").status_code == status


def test_admin_routes_allow_granted_user():
    client = client_for(7, allowed=True)
    check = client.get("/admin/check")
    assert check.status_code == 204
    assert check.headers["x-kervion-admin-id"] == "kervion-7"
    page = client.get("/admin/audit")
    assert page.status_code == 200
    assert "보안 감사 대시보드" in page.text
    assert "감사 이벤트 현황" in page.text
    assert 'src="/api/v1/admin/grafana/d/kervion-security-audit/' in page.text
    assert page.headers["cache-control"] == "no-store"


def test_login_cookie_reaches_admin_page_and_clears_old_path():
    response = Response()
    _set_cookie(response, "test-token")
    cookies = response.headers.getlist("set-cookie")
    assert any("kervion_session=test-token" in cookie and "Path=/;" in cookie for cookie in cookies)
    assert any("Path=/api/v1;" in cookie and "Max-Age=0" in cookie for cookie in cookies)
