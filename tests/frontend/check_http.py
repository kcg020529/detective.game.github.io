import json
import sys
from _server import frontend_url
from playwright.sync_api import sync_playwright

# J03 http 모드: 가짜 서버(route)로 api.js의 fetch 경로 확인
URL = frontend_url()
BASE = "http://api.test/api/v1"
results, seen, errors = [], [], []

SAVE = {"save_id": 101, "slot_no": 1, "role": "grad", "day": 2, "clue_count": 0,
        "created_at": "2026-10-16 12:00:00", "last_played_at": "2026-10-16 12:00:00"}


def check(name, ok, extra=""):
    results.append(("OK " if ok else "FAIL ") + name + (f" | {extra}" if extra else ""))
    print(results[-1], flush=True)


def handler(route):
    req = route.request
    path = req.url.replace(BASE, "")
    seen.append((req.method, path, req.post_data, req.headers.get("authorization")))
    def ok(body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body),
                      headers={"access-control-allow-origin": URL.rstrip("/"), "access-control-allow-credentials": "true"})
    if req.method == "OPTIONS":
        return route.fulfill(status=204, headers={"access-control-allow-origin": URL.rstrip("/"), "access-control-allow-credentials": "true", "access-control-allow-headers": "content-type, authorization", "access-control-allow-methods": "GET, POST, PUT"})
    if path == "/auth/login" and json.loads(req.post_data).get("password") == "wrong":
        return ok({"error": {"code": "AUTH_REQUIRED", "message": "아이디 또는 비밀번호가 맞지 않습니다.", "request_id": "r"}}, 401)
    if path == "/auth/login":
        return ok({"user_id": 7, "username": "researcher01", "access_token": "tok123"})
    if path == "/saves":
        return ok({"saves": [SAVE]})
    if path == "/auth/logout":  # 많은 서버가 204 빈 본문으로 응답
        return route.fulfill(status=204, headers={"access-control-allow-origin": URL.rstrip("/"), "access-control-allow-credentials": "true"})
    if path.startswith("/saves/101/chats/YB-2") and req.method == "GET":  # DB 행 모양, 모르는 응답 종류
        return ok({"messages": [
            {"message_id": 5, "ai_id": "YB-2", "sender": "ai", "content": "a0", "response_type": "partial", "created_at": "2026-10-16 12:00:00"},
            {"message_id": 6, "ai_id": "YB-2", "sender": "user", "content": "q1", "response_type": None, "created_at": "2026-10-16 12:00:01"},
            {"message_id": 7, "ai_id": "YB-2", "sender": "ai", "content": "a1", "response_type": "weird", "created_at": "2026-10-16 12:00:02"}], "has_more": True})
    if path == "/saves/101/chats/YB-2" and req.method == "POST":
        return ok({"request_id": "r1", "messages": [
            {"message_id": 8, "ai_id": "YB-2", "sender": "user", "content": "hi", "response_type": None, "created_at": "x"},
            {"message_id": 9, "ai_id": "YB-2", "sender": "ai", "content": "yo", "response_type": "restricted", "created_at": "x"}],
            "new_clues": [], "game_state": {"current_day": 2}})
    if path == "/auth/signup":
        return ok({"user_id": 8, "username": "newbie", "roles": ["std"]}, 201)
    if path == "/saves/101/chats/YB-9?limit=20":  # 200인데 필드 누락
        return ok({})
    if path == "/saves/102":
        return route.fulfill(status=502, content_type="text/html", body="<html>Bad Gateway</html>",
                             headers={"access-control-allow-origin": URL.rstrip("/"), "access-control-allow-credentials": "true"})
    return ok({"error": {"code": "NOT_FOUND", "message": "없음", "request_id": "req_x"}}, 404)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.on("pageerror", lambda e: errors.append(f"pageerror {e}"))
    pg.on("console", lambda m: m.type == "error" and "favicon" not in m.text and not m.text.startswith("Failed to load resource:") and errors.append(f"console {m.text}"))
    pg.add_init_script(f"window.KERVION_API_BASE = '{BASE}'")
    pg.route("http://api.test/**", handler)
    pg.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.url.startswith(URL) and r.status >= 400 else None)
    pg.goto(URL)
    check("mode http", pg.evaluate("Api.mode") == "http")
    pg.wait_for_selector("#start-button:not([hidden])", timeout=30000)
    pg.click("#start-button")
    pg.fill("#login-id", "researcher01")
    pg.fill("#login-pw", "wrong")
    pg.click("#login-submit")
    pg.wait_for_timeout(800)
    check("login 401 → server message, id kept", "맞지 않습니다" in pg.inner_text("#login-message") and "만료" not in pg.inner_text("#login-message") and pg.input_value("#login-id") == "researcher01", pg.inner_text("#login-message"))
    pg.fill("#login-pw", "x")
    pg.click("#login-submit")
    pg.wait_for_selector("#lobby-view:not([hidden])", timeout=8000)
    check("login + saves via fetch", True, pg.inner_text("#continue-info"))
    check("login body", json.loads([d for m, pth, d, a in seen if pth == "/auth/login"][-1]) == {"username": "researcher01", "password": "x"})

    # 날짜: DB DATETIME 그대로 (시간대 없음)
    pg.click("#menu-continue")
    pg.wait_for_selector("[data-slot='0']", timeout=8000)
    pg.wait_for_timeout(800)
    check("DATETIME string displayed", "10월 16일" in pg.inner_text("[data-slot='0']"), pg.inner_text("[data-slot='0']").replace("\n", " "))

    # 오류 본문이 JSON 아닌 502
    err = pg.evaluate("Api.getSave(102).then(() => 'ok', e => [e.status, e.code, e.message])")
    check("502 html body → SERVICE_UNAVAILABLE", isinstance(err, list) and err[1] == "SERVICE_UNAVAILABLE", str(err))
    err = pg.evaluate("Api.listChats(101, 'YB-9').then(r => ['ok', r], e => ['err', e.code])")
    check("200 missing array field → error, not crash", err == ["err", "INVALID_RESPONSE"], str(err))
    # 계약 모양 404
    err = pg.evaluate("Api.getSave(999).then(() => 'ok', e => [e.status, e.code, e.message, e.requestId])")
    check("404 error parsed", err == [404, "NOT_FOUND", "없음", "req_x"], str(err))
    # 쿠키 방식: Authorization 헤더 없음, 채팅 목록 쿼리
    check("no Authorization header", all(a is None for m, pth, d, a in seen), str({a for m, pth, d, a in seen}))
    pg.evaluate("Api.listChats(101, 'YB-1', 55).catch(() => null)")
    check("listChats query", any(pth == "/saves/101/chats/YB-1?limit=20&before=55" for m, pth, d, a in seen), str([pth for m, pth, d, a in seen if "chats" in pth]))
    # 채팅: DB 행 모양
    rows = pg.evaluate("Api.listChats(101, 'YB-2').then(r => r.messages.map(m => m.response_type))")
    check("chat rows normalized (weird → unknown)", rows == ["partial", None, "unknown"], str(rows))
    sent = pg.evaluate("Api.sendChat(101, 'YB-2', 'hi', 'cid-1').then(r => r.messages.map(m => m.sender + ':' + m.response_type))")
    post = next((d for m, pth, d, a in seen if m == "POST" and pth == "/saves/101/chats/YB-2"), None)
    check("sendChat path + body", sent == ["user:null", "ai:restricted"] and json.loads(post) == {"message": "hi", "client_request_id": "cid-1"}, f"{sent} {post}")
    su = pg.evaluate("Api.signup('newbie', 'pw', 'std')")
    body = json.loads(next(d for m, pth, d, a in seen if pth == "/auth/signup"))
    check("signup sends role, returns roles", body == {"username": "newbie", "password": "pw", "role": "std"} and su["roles"] == ["std"], f"{body} {su}")
    # 204 로그아웃
    out = pg.evaluate("Api.logout().then(r => ['ok', r], e => ['err', e.code])")
    check("logout 204 ok", out[0] == "ok", str(out))
    b.close()

print("errors:", errors)
failed = any(item.startswith("FAIL ") for item in results) or bool(errors)
sys.exit(1 if failed else 0)
